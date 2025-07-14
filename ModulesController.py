import time
from pi74HC595 import pi74HC595
import RPi.GPIO as gpio
from HX711_2 import HX711
from StatesManager import StatesManager
import neopixel
import board


class EComponent:
    WEIGHT_CELL = 1
    MAIN_PUMP = 2
    VALVE = 3
    FLUSH_PUMP = 4


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

    def get_all_weights(self):
        return self.modules_weights

    # region register
    def set_main_pump_state(self, module, on):
        # '-' first module is last to receive data
        self.modules_states[module * self.bits + EComponent.MAIN_PUMP] = on

    def set_flush_pump_state(self, module, on):
        self.modules_states[module * self.bits + EComponent.FLUSH_PUMP] = on

    def set_weight_cell_state(self, module, on):
        self.modules_states[module * self.bits + EComponent.WEIGHT_CELL] = on

    def set_valve_state(self, module, open):
        self.modules_states[module * self.bits + EComponent.VALVE] = open

    def send_states(self):
        self.shift_register.set_by_list(self.modules_states[::-1])
    # endregion

    # region weight_cells
    def read_weight(self, module):
        self.set_weight_cell_state(module, True)
        self.send_states()
        sm = StatesManager()
        sensor = HX711(self.ws_dout_pin, self.ws_clock_pin)
        sensor.set_reference_unit_A(sm.get_weight_cell_reference_unit(module))
        sensor.set_offset(sm.get_weight_cell_offset(module))
        val = sensor.get_weight()
        self.modules_weights[module] = val
        self.set_weight_cell_state(module, False)
        self.send_states()
        return True

    def read_all_weights(self):
        for i in range(self.nb_modules):
            self.read_weight(i)
        return True

    def tare_weight_cell(self, module):
        self.set_weight_cell_state(module, True)
        self.send_states()
        sm = StatesManager()
        sensor = HX711(self.ws_dout_pin, self.ws_clock_pin)
        sensor.set_reference_unit(sm.get_weight_cell_reference_unit(module))
        sensor.tare(10)
        sm.set_weight_cell_offset(module, sensor.OFFSET)
        self.set_weight_cell_state(module, False)
        self.send_states()
        return True

    def tare_all_cells(self):
        for i in range(self.nb_modules):
            self.tare_weight_cell(i)
        return True
    # endregion

    # region serve
    def flush(self, module, pre_send=True, post_send=True):
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
        self.set_main_pump_state(module, on=True)
        if pre_send:
            self.send_states()

        time.sleep(_time)

        self.set_main_pump_state(module, on=False)
        if post_send:
            self.send_states()
        return True

    def serve(self, module, quantity, post_send=True):
        _time = quantity * StatesManager().get_pump_speed_ratio(module) * StatesManager().get_sec_per_liter()

        self.flush(module, post_send=False)
        self.pump(module, _time, post_send=False)
        self.flush(module, post_send=post_send)

    def blend(self, mix, cup_size, status_callback):
        for module, ratio in mix.items():
            self.serve(module, cup_size * ratio, post_send=False)  # chain state send with other
        self.send_states()
        return True

    def faster_blend(self, mix, cup_size, status_callback):
        mix = list(mix.items())

        module_0 = mix[0][0]
        ratio_0 = mix[0][1]
        self.flush(module_0, post_send=False)
        self.pump(module_0, cup_size * ratio_0, post_send=False)

        for i in range(1, len(mix)):
            prev_module, _ = mix[i-1]
            module, ratio = mix[i]

            # make both flush at the same time !
            # region flush
            self.set_valve_state(prev_module, open=True)
            self.set_flush_pump_state(prev_module, on=True)
            self.set_valve_state(module, open=True)
            self.set_flush_pump_state(module, on=True)

            time.sleep(3)

            self.set_valve_state(prev_module, open=False)
            self.set_flush_pump_state(prev_module, on=False)
            self.set_valve_state(module, open=False)
            self.set_flush_pump_state(module, on=False)
            # endregion

            self.pump(module, cup_size * ratio)

        self.flush(mix[-1][0])
        return True
    # endregion

    def cleanup(self):
        self.shift_register.clear()
