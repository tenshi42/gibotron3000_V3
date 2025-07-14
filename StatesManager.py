import json


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class StatesManager(metaclass=Singleton):
    def __init__(self):
        self.states_file_path = r"states.json"
        self.states = {}

    def load_states(self):
        with open(self.states_file_path, 'r', encoding='utf-8') as f:
            self.states = json.load(f)

    def save_states(self):
        with open(self.states_file_path, 'w+') as f:
            json.dump(self.states, f, indent=4)

    # region pump
    # region get
    def get_pump_enabled(self, module):
        return self.states["pumps"][module]["enabled"]

    def get_pump_speed_ratio(self, module):
        return self.states["pumps"][module]["speed_ratio"]

    def get_pump_delay_for_distance(self, module):
        return self.states["pumps"][module]["delay_for_distance"]

    def get_full_pump_state(self, module):
        return self.states["pumps"][module]

    def get_all_full_pump_states(self):
        return self.states["pumps"]
    # endregion

    # region set
    def set_pump_enabled(self, module, enabled):
        self.states["pumps"][module]["enabled"] = enabled
        self.save_states()

    def set_pump_speed_ratio(self, module, speed_ratio):
        self.states["pumps"][module]["speed_ratio"] = speed_ratio
        self.save_states()

    def set_pump_delay_for_distance(self, module, delay):
        self.states["pumps"][module]["delay_for_distance"] = delay
        self.save_states()
    # endregion
    # endregion

    # region weight_cell
    # region get
    def get_weight_cell_offset(self, module):
        return self.states["weight_cells"][module]["offset"]

    def get_weight_cell_reference_unit(self, module):
        return self.states["weight_cells"][module]["reference_unit"]
    # endregion

    # region set
    def set_weight_cell_offset(self, module, offset):
        self.states["weight_cells"][module]["offset"] = offset
        self.save_states()

    def set_weight_cell_reference_unit(self, module, reference_unit):
        self.states["weight_cells"][module]["reference_unit"] = reference_unit
        self.save_states()
    # endregion
    # endregion

    def get_sec_per_liter(self):
        return self.states["sec_per_liter"]

    def set_sec_per_liter(self, value):
        self.states["sec_per_liter"] = value
        self.save_states()

