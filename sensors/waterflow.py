"""Compatibility wrapper around the shared YF-S201 driver."""
from sensors.YF_S201 import YFS201


class FlowSensor(YFS201):
    def __init__(self, pin=None, pulses_per_liter=None):
        super().__init__(GPIO_YF=pin, pulses_per_liter=pulses_per_liter)
        self.pin = self.GPIO_YF

    def read_flow_rate(self, window_sec=1.0):
        return super().read_flow_rate(duration=window_sec)
