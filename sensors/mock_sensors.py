"""
Mock sensor layer for testing WITHOUT hardware.
Produces realistic data with random variation and scheduled danger scenarios,
so the alarm logic, database, and API publisher can be fully tested on a desktop/Pi.

Active when EFWS_RUN_MODE=mock.
"""
import logging
import random
import time

from config import settings


# ─── Helper ──────────────────────────────────────────────────────
def _jitter(value: float, pct: float = 0.05) -> float:
    """Add random noise of ±pct% to the value."""
    return round(value * (1 + random.uniform(-pct, pct)), 3)


# ─── Base mock ────────────────────────────────────────────────────
class _MockBase:
    """All mock sensors derive from this; _scenario() can be overridden."""

    def _scenario(self) -> str:
        """Pick a scenario based on time (2-minute cycle for the demo)."""
        t = time.time() % 120          # 120-second cycle
        if t < 80:
            return "normal"
        elif t < 100:
            return "warning"
        else:
            return "critical"


# ─── Submersible Pressure Sensor (water level, 4-20mA loop) ──────
class MockPressureWater(_MockBase):
    MA_BASE = {"normal": 5.0, "warning": 9.0, "critical": 17.0}
    RANGE_M = settings.PRESSURE_RANGE_M

    def read(self) -> dict:
        sc   = self._scenario()
        ma   = max(4.0, min(20.0, _jitter(self.MA_BASE[sc], 0.05)))
        pct  = max(0.0, min(1.0, (ma - 4.0) / 16.0))
        depth = round(pct * self.RANGE_M, 3)
        return {
            "current_ma":     round(ma, 3),
            "depth_m":        depth,
            "pressure_bar":   round(depth * 0.0980665, 4),
            "fault_open_loop": False,
            "_mock": True, "_scenario": sc,
        }


# ─── Rainfall ────────────────────────────────────────────────────
class MockRainfall(_MockBase):
    RAINFALL_BASE = {"normal": 0.2, "warning": 12.0, "critical": 35.0}

    def read(self) -> dict:
        sc          = self._scenario()
        rainfall_mm = max(0.0, _jitter(self.RAINFALL_BASE[sc], 0.08))
        return {
            "rainfall_last_hour_mm": round(rainfall_mm, 3),
            "rainfall_total_mm":     round(rainfall_mm * 4, 3),
            "tip_counter":           int(rainfall_mm / 0.2794),
            "working_time_hours":    24.0,
            "_mock": True, "_scenario": sc,
        }

# ─── Battery — DC 0-25V Voltage Sensor Module ────────────────────
class MockBattery(_MockBase):
    PCT_BASE = {"normal": 85.0, "warning": 42.0, "critical": 15.0}

    def read(self) -> dict:
        sc  = self._scenario()
        pct = max(0.0, min(100.0, _jitter(self.PCT_BASE[sc], 0.04)))
        v = round(settings.BATTERY_MIN_V + pct / 100 * (settings.BATTERY_MAX_V - settings.BATTERY_MIN_V), 2)
        return {"voltage": v, "percent": round(pct, 1), "_mock": True, "_scenario": sc}


# ─── Mock Alarm (no GPIO) ────────────────────────────────────────
class MockAlarmController:
    """Print the alarm level to the console; does not touch GPIO."""

    LEVELS = {"none": "🟢", "warning": "🟡", "critical": "🔴"}
    current_level = "none"

    def set_level(self, level: str):
        if level == self.current_level:
            return
        self.current_level = level
        logging.getLogger("efws.mock").info("Mock alarm: %s", level)

    def silence(self):
        self.set_level("none")



class MockWaterflow:
    def __init__(self):
        self._last_read = time.monotonic()
        self._total_liters = 0.0

    def read(self):
        now = time.monotonic()
        elapsed = now - self._last_read
        self._last_read = now
        flow = _jitter(5.0)
        self._total_liters += flow * elapsed / 60
        return {"flow_lpm": flow, "total_liters": round(self._total_liters, 4),
                "sample_duration_sec": elapsed, "_mock": True}


class MockDistance(_MockBase):
    def read(self):
        return _jitter({"normal": 2.5, "warning": 1.5, "critical": 0.5}[self._scenario()])


class MockBME280(_MockBase):
    def read(self):
        return {"temperature_c": _jitter(26.0), "humidity_percent": _jitter(65.0),
                "pressure_hpa": _jitter(1013.0, 0.001), "_mock": True}


class MockAnemometer(_MockBase):
    def read(self):
        return {"speed_ms": _jitter(3.0), "_mock": True}


class MockWindDirection(_MockBase):
    def read(self):
        return {"direction_code": 2, "direction_abbr": "NE", "direction_name": "Northeast", "_mock": True}


class MockAQI(_MockBase):
    """Synthetic particulate readings using the same ISPU and averaging as hardware."""

    def __init__(self):
        from sensors.aqi import WindowMean

        self._avg25 = WindowMean(settings.AQI_WINDOW_SEC)
        self._avg10 = WindowMean(settings.AQI_WINDOW_SEC)
        self._started = time.monotonic()

    def read(self):
        from sensors.aqi import ispu

        pm25 = _jitter({"normal": 8.0, "warning": 35.0, "critical": 100.0}[self._scenario()])
        pm1, pm10 = round(pm25 * 0.6, 3), round(pm25 * 1.5, 3)
        self._avg25.add(pm25)
        self._avg10.add(pm10)
        value, _, _ = ispu(self._avg25.mean(), self._avg10.mean())
        return {"pm1": pm1, "pm25": pm25, "pm10": pm10, "aqi": value,
                "provisional": time.monotonic() - self._started < settings.AQI_WINDOW_SEC, "_mock": True}
