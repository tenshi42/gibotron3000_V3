import time

from RPi import GPIO
from pi74HC595 import pi74HC595
import RPi.GPIO as gpio
from HX711_2 import HX711
from StatesManager import StatesManager
import neopixel
import board


DEBUG_MODE = True


class EComponent:
    FLUSH_PUMP = 1
    MAIN_PUMP = 2
    VALVE = 3
    WEIGHT_CELL = 4


class ModulesController:
    def __init__(self):
        gpio.setmode(gpio.BCM)

        self.nb_modules = 8
        self.bits = 8

        self.initial_blend_time = 0
        self.remaining_blend_time = 0

        self.enable_pin = 22
        gpio.setup(self.enable_pin, gpio.OUT)
        gpio.output(self.enable_pin, gpio.HIGH)

        StatesManager().load_states()

        # _, weight_cell, main_pump, valve, small_motor, _, _, _
        self.modules_states = [False for _ in range(self.nb_modules * self.bits)]

        # shift_registers
        self.sr_data_pin = 10
        self.sr_latch_pin = 12
        self.sr_clock_pin = 14
        self.shift_register = pi74HC595(self.sr_data_pin, self.sr_latch_pin, self.sr_clock_pin, self.nb_modules)
        self.send_states()

        # weight_sensors
        self.ws_dout_pin = 9
        self.ws_clock_pin = 11
        self.modules_weights = [0 for _ in range(self.nb_modules)]

        # led_strip
        self.ls_nb_leds = 1
        self.ls_pin = board.D21  # GPIO_13
        self.ls_order = neopixel.GRB
        self.led_strip = neopixel.NeoPixel(self.ls_pin, self.ls_nb_leds, brightness=0.5, auto_write=False, pixel_order=self.ls_order)
        self.led_strip.fill((255, 255, 255))

        gpio.output(self.enable_pin, gpio.LOW)

        self.init_load_cells()

    def read_dout(self):
        GPIO.setup(self.ws_dout_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        print(f"dout : {GPIO.input(self.ws_dout_pin)}")
        # GPIO.cleanup(self.ws_dout_pin)

    def init_load_cells(self):
        for i in range(self.nb_modules):
            if StatesManager().get_pump_enabled(i):
                StatesManager().set_pump_enabled(i, StatesManager().get_weight_cell_offset(i) != 0)
        self.read_all_weights()

    def get_all_weights(self):
        return self.modules_weights

    # region register
    def set_main_pump_state(self, module, on):
        if DEBUG_MODE:
            print("::set_main_pump_state", module, on)
        # '-' first module is last to receive data
        self.modules_states[module * self.bits + EComponent.MAIN_PUMP] = on

    def set_flush_pump_state(self, module, on):
        if DEBUG_MODE:
            print("::set_flush_pump_state", module, on)
        self.modules_states[module * self.bits + EComponent.FLUSH_PUMP] = on

    def set_weight_cell_state(self, module, on):
        if DEBUG_MODE:
            print("::set_weight_cell_state", module, on)
        self.modules_states[module * self.bits + EComponent.WEIGHT_CELL] = on

    def set_valve_state(self, module, open):
        if DEBUG_MODE:
            print("::set_valve_state", module, open)
        self.modules_states[module * self.bits + EComponent.VALVE] = open

    def send_states(self):
        for i in range(4):
            print([1 if x else 0 for x in self.modules_states][i*8:i*8+8])
        self.shift_register.set_by_list(self.modules_states[::-1])
    # endregion

    # region weight_cells
    def read_weight(self, module):
        module = int(module)

        self.set_weight_cell_state(module, True)
        self.send_states()
        sm = StatesManager()
        sensor = HX711(self.ws_dout_pin, self.ws_clock_pin)
        sensor.set_reading_format("MSB", "MSB")
        sensor.reset()
        sensor.set_reference_unit_A(sm.get_weight_cell_reference_unit(module))
        sensor.set_offset(sm.get_weight_cell_offset(module))
        val = sensor.get_weight(10)
        sensor.power_down()
        sensor.stop()
        self.modules_weights[module] = val
        self.set_weight_cell_state(module, False)
        self.send_states()
        return True

    def read_some_weights(self, modules):
        for i in modules:
            self.read_weight(int(i))

    def read_all_weights(self):
        for i in range(self.nb_modules):
            if StatesManager().get_pump_enabled(i):
                self.read_weight(i)
        return True

    def tare_weight_cell(self, module):
        module = int(module)

        if not StatesManager().get_pump_enabled(module):
            return False

        self.set_weight_cell_state(module, True)
        self.send_states()
        sm = StatesManager()
        time.sleep(0.1)
        sensor = HX711(self.ws_dout_pin, self.ws_clock_pin)
        sensor.set_reading_format("MSB", "MSB")
        sensor.reset()
        sensor.set_reference_unit(sm.get_weight_cell_reference_unit(module))
        sensor.tare(10)
        sensor.power_down()
        sensor.stop()
        sm.set_weight_cell_offset(module, sensor.OFFSET)
        self.set_weight_cell_state(module, False)
        self.send_states()
        return True

    def tare_all_cells(self):
        for i in range(self.nb_modules):
            if StatesManager().get_pump_enabled(i):
                self.tare_weight_cell(i)
        return True
    # endregion

    # region serve
    def flush(self, module, pre_send=True, post_send=True):
        if DEBUG_MODE:
            print("flush", module, pre_send, post_send)
        module = int(module)

        self.set_valve_state(module, open=True)
        self.set_flush_pump_state(module, on=True)
        if pre_send:
            self.send_states()

        time.sleep(3)

        self.set_valve_state(module, open=False)
        self.set_flush_pump_state(module, on=False)
        if post_send:
            self.send_states()
        return True

    def pump(self, module, _time, pre_send=True, post_send=True):
        if DEBUG_MODE:
            print("pump", module, _time, pre_send, post_send)

        module = int(module)
        self.set_main_pump_state(module, on=True)
        if pre_send:
            self.send_states()

        time.sleep(_time)

        self.set_main_pump_state(module, on=False)
        if post_send:
            self.send_states()
        return True

    def serve(self, module, quantity, post_send=True):
        module = int(module)
        _time = quantity * StatesManager().get_pump_speed_ratio(module) * StatesManager().get_sec_per_liter()

        self.flush(module, post_send=False)
        self.pump(module, _time, post_send=False)
        self.flush(module, post_send=post_send)

    def blend(self, data, status_callback):
        # handle callback
        mix, cup_size = data['ratios'], data['cup_size']
        for module, ratio in mix.items():
            self.serve(module, cup_size * ratio, post_send=False)
        self.send_states()

        self.read_some_weights(list(mix.keys()))

        return True

    def faster_blend(self, data, status_callback):
        mix, cup_size = data['ratios'], data['cup_size']
        mix = list(mix.items())

        module_0 = int(mix[0][0])
        ratio_0 = mix[0][1]

        self.flush(module_0, post_send=False)

        _time = cup_size * ratio_0 * StatesManager().get_pump_speed_ratio(module_0) * StatesManager().get_sec_per_liter()
        self.pump(module_0, _time, post_send=False)

        for i in range(1, len(mix)):
            prev_module, _ = mix[i-1]
            module, ratio = mix[i]
            prev_module = int(prev_module)
            module = int(module)

            # make both flush at the same time !
            # region flush
            self.set_valve_state(prev_module, open=True)
            self.set_flush_pump_state(prev_module, on=True)
            self.set_valve_state(module, open=True)
            self.set_flush_pump_state(module, on=True)
            self.send_states()

            time.sleep(3)

            self.set_valve_state(prev_module, open=False)
            self.set_flush_pump_state(prev_module, on=False)
            self.set_valve_state(module, open=False)
            self.set_flush_pump_state(module, on=False)
            self.send_states()
            # endregion

            _time = cup_size * ratio * StatesManager().get_pump_speed_ratio(module) * StatesManager().get_sec_per_liter()
            self.pump(module, _time)

        self.flush(int(mix[-1][0]))

        self.read_some_weights(list(data['ratios'].keys()))

        return True
    # endregion

    def cleanup(self):
        self.shift_register.clear()
