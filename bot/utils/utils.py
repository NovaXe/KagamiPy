

def clamp(num, min_value, max_value):
    num = max(min(num, max_value), min_value)
    return num


def seconds_to_time(seconds: int):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60




    return hours, minutes, seconds



class ClampedValue:
    def __init__(self, value: int | float, min_value, max_value):
        self._value = value
        # self.type = type(value)
        self.min_value = min_value
        self.max_value = max_value

    def __get__(self, obj, obj_type=None):
        self._value = max(min(self._value, self.max_value), self.min_value)
        print(self._value)
        return self._value

    def __set__(self, obj, value: int | float):
        self._value = max(min(value, self.max_value), self.min_value)
        print(self._value)

    def __add__(self, value: int | float):
        self._value = self._value + value

    def __sub__(self, value: int | float):
        self._value = self._value - value

    def __mul__(self, multiplier: int | float):
        self._value = self._value * multiplier

    def __truediv__(self, dividend: int | float):
        self._value = self._value / dividend

    def __floordiv__(self, dividend: int | float):
        self._value = self._value // dividend

    def __int__(self):
        return int(self._value)

    def __float__(self):
        return float(self._value)



