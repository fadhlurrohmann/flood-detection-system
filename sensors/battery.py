"""
Modul Sensor Tegangan DC 0-25V — monitoring baterai (voltage divider bawaan modul).
Pin S langsung ke MCP3008 CH3.

Input : terhubung langsung ke terminal Battery+ dan Battery-
Output: pin S → 0-5V proporsional terhadap tegangan input (0-25V)

Kalkulasi:
  V_s       = raw / 1023 × MCP3008_VREF
  V_battery = V_s × BATTERY_DIVIDER_RATIO        (modul 30k/7.5k → ÷5)
  Baterai 14.4V → V_s 2.88V, masih di bawah VREF 3.3V.
"""
import statistics

from config import settings
from sensors.mcp3008 import get_mcp3008


class BatterySensor:
    SAMPLES = 9   # median dari N sampel cepat → buang spike noise ADC

    def __init__(self, channel=None, divider_ratio=None, vref=None, batt_max_v=None, batt_min_v=None):
        self.channel      = channel      if channel      is not None else settings.ADC_CHANNEL_BATTERY
        self.ratio        = divider_ratio if divider_ratio is not None else settings.BATTERY_DIVIDER_RATIO
        self.vref         = vref         if vref         is not None else settings.MCP3008_VREF
        self.batt_max_v   = batt_max_v   if batt_max_v   is not None else settings.BATTERY_MAX_V
        self.batt_min_v   = batt_min_v   if batt_min_v   is not None else settings.BATTERY_MIN_V
        self.adc          = get_mcp3008()

    def read_raw(self) -> int:
        samples = [self.adc.read_raw(self.channel) for _ in range(self.SAMPLES)]
        return int(statistics.median(samples))

    def raw_to_voltage(self, raw: int) -> float:
        return round(raw / 1023.0 * self.vref * self.ratio, 3)

    def read_voltage(self) -> float:
        return self.raw_to_voltage(self.read_raw())

    def voltage_to_percent(self, v: float) -> float:
        span = self.batt_max_v - self.batt_min_v
        pct  = (v - self.batt_min_v) / span * 100
        return round(max(0.0, min(100.0, pct)), 1)

    def read_percent(self) -> float:
        return self.voltage_to_percent(self.read_voltage())

    def read(self) -> dict:
        v = self.read_voltage()   # satu pembacaan → voltage & percent konsisten
        return {"voltage": v, "percent": self.voltage_to_percent(v)}


if __name__ == "__main__":
    import time
    sensor = BatterySensor()
    while True:
        print(sensor.read())
        time.sleep(2)
