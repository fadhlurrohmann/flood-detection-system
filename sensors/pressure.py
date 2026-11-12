"""
Submersible Pressure Sensor
Output : 4-20mA

Configuration:
- MCP3008
- Raspberry Pi
- WITHOUT Logic Level Converter
- Burden resistor = 100 Ohm
- ADC Reference = 3.3V

Voltage produced:

4mA
0.4V

20mA
2.0V

Safe for MCP3008.
"""

import math

from config import settings
from sensors.mcp3008 import get_mcp3008


class PressureWaterSensor:

    def __init__(
        self,
        channel=None,
        burden_ohm=None,
        adc_ref_voltage=None,
        min_ma=None,
        max_ma=None,
        range_m=None,
    ):

        self.channel = (
            channel
            if channel is not None
            else settings.ADC_CHANNEL_PRESSURE
        )

        self.burden_ohm = (
            burden_ohm
            if burden_ohm is not None
            else settings.PRESSURE_BURDEN_OHM
        )

        self.adc_ref = (
            adc_ref_voltage
            if adc_ref_voltage is not None
            else settings.PRESSURE_ADC_REF_VOLTAGE
        )

        self.min_ma = (
            min_ma
            if min_ma is not None
            else settings.PRESSURE_MIN_MA
        )

        self.max_ma = (
            max_ma
            if max_ma is not None
            else settings.PRESSURE_MAX_MA
        )

        self.range_m = (
            range_m
            if range_m is not None
            else settings.PRESSURE_RANGE_M
        )

        values = (self.burden_ohm, self.adc_ref, self.min_ma, self.max_ma, self.range_m)
        if not all(math.isfinite(v) and v > 0 for v in values) or self.max_ma <= self.min_ma:
            raise ValueError("Invalid pressure calibration")
        self.adc = get_mcp3008()

    # ------------------------------------------------------

    def read_raw(self):

        return self.adc.read_raw(self.channel)

    # ------------------------------------------------------

    def read_voltage(self):

        raw = self.read_raw()

        voltage = raw / 1023.0 * self.adc_ref

        return round(voltage, 4)

    # ------------------------------------------------------

    def read_current_ma(self):

        voltage = self.read_voltage()

        current_ma = voltage / self.burden_ohm * 1000.0

        return round(current_ma, 3)

    # ------------------------------------------------------

    def read_depth_m(self):

        current = self.read_current_ma()

        percent = (
            current - self.min_ma
        ) / (
            self.max_ma - self.min_ma
        )

        percent = max(
            0.0,
            min(1.0, percent)
        )

        return round(
            percent * self.range_m,
            3
        )

    # ------------------------------------------------------

    def read_pressure_bar(self):

        depth = self.read_depth_m()

        pressure = depth * 0.0980665

        return round(
            pressure,
            4
        )

    # ------------------------------------------------------

    def read(self):

        raw = self.read_raw()

        # Derive all fields from one ADC sample so faults and depth agree.
        voltage = round(raw / 1023.0 * self.adc_ref, 4)
        current = round(voltage / self.burden_ohm * 1000.0, 3)
        fault = current < self.min_ma - 0.2
        out_of_range = fault or current > self.max_ma + 0.5 or raw >= 1023
        fraction = max(0.0, min(1.0, (current - self.min_ma) / (self.max_ma - self.min_ma)))
        depth = None if out_of_range else round(fraction * self.range_m, 3)
        pressure = None if depth is None else round(depth * 0.0980665, 4)

        return {

            "adc_raw": raw,

            "voltage": voltage,

            "current_ma": current,

            "depth_m": depth,

            "pressure_bar": pressure,

            "fault_open_loop": fault,
            "fault_out_of_range": out_of_range,

        }


if __name__ == "__main__":

    import time

    sensor = PressureWaterSensor()

    while True:

        print(sensor.read())

        time.sleep(2)
