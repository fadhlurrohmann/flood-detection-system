"""
Mock sensor layer for testing WITHOUT hardware.
Produces realistic data with random variation and scheduled danger scenarios,
so the alarm logic, database, and API publisher can be fully tested on a desktop/Pi.

Active when EFWS_RUN_MODE=mock (default).
"""
import math
import random
import time


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
    MA_BASE = {"normal": 14.0, "warning": 7.0, "critical": 4.5}  # lower = shallower/emptier
    RANGE_M = 5.0

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
            "rainfall_mm":           round(rainfall_mm, 3),
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
        v   = round(9.0 + pct / 100 * 3.6, 2)
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
        icon = self.LEVELS.get(level, "⚪")
        print(f"  [ALARM] {icon}  Level → {level.upper()}")

    def silence(self):
        self.set_level("none")

