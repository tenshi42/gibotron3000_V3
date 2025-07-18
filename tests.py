import time

from HX711_2 import HX711
import RPi.GPIO as gpio

from ModulesController import ModulesController


def aatest_cell():
    gpio.setmode(gpio.BCM)
    cell = HX711(9, 11)

    # cell.set_scale(87834)
    cell.set_reference_unit_A(203)

    val = cell.get_weight()
    print(val)

    # cell.set_offset(-475590)
    cell.tare()
    print("offset : ", cell.OFFSET)

    for i in range(100):
        val = cell.get_weight()
        print(val)
        time.sleep(1)


def aatest_module():
    module = ModulesController()
    for i in range(10):
        state = i % 2 == 0
        print(state)
        module.set_flush_pump_state(0, state)
        module.send_states()
        time.sleep(1)


def aatest_module_weight():
    module = ModulesController()
    # module.tare_weight_cell(0)
    module.read_weight(0)
    print(module.get_all_weights())


if __name__ == '__main__':
    aatest_cell()
    # aatest_module()
    # aatest_module_weight()

    """a = [1,2,3,4,5]
    print(a)
    print(a[::-1])"""