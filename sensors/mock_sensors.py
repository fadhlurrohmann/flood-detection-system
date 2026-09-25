"""
Mock sensor layer for testing WITHOUT hardware.
Generates data realistis with variasi random and skenario danger scheduled,
so alarm logic, database, and API publisher can diuji full in desktop/Pi.

Active when EFWS_RUN_MODE=mock (default).
"""
import math
import random
import time


# ─── Helper ──────────────────────────────────────────────────────
def _jitter(value: float, pct: float = 0.05) -> float:
    """Add noise random ±pct% to value."""
    return round(value * (1 + random.uniform(-pct, pct)), 3)


# ─── Base mock ────────────────────────────────────────────────────
class _MockBase:
    """All mock sensor derived from here; _scenario() can override."""

    def _scenario(self) -> str:
        """Select skenario based on time (cycle 2 minutes for demo)."""
        t = time.time() % 120          # cycle 120 seconds
        if t < 80:
            return "normal"
        elif t < 100:
            return "warning"
        else:
            return "critical"


# ─── Submersible Pressure Sensor (water level, loop 4-20mA) ──────
class MockPressureWater(_MockBase):
    MA_BASE = {"normal": 14.0, "warning": 7.0, "critical": 4.5}  # increasingly low = increasingly shallow/empty
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


# ─── Soil moisture ───────────────────────────────────────────────
class MockSoilMoisture(_MockBase):
    SURFACE_BASE = {"normal": 55.0, "warning": 18.0, "critical":  8.0}
    DEEP_BASE    = {"normal": 65.0, "warning": 25.0, "critical": 12.0}

    def read(self) -> dict:
        sc          = self._scenario()
        surface_pct = max(0.0, _jitter(self.SURFACE_BASE[sc], 0.06))
        deep_pct    = max(0.0, _jitter(self.DEEP_BASE[sc],    0.06))
        return {
            "surface": {"raw": int(900 - surface_pct / 100 * 520), "moisture_percent": round(surface_pct, 2), "_mock": True},
            "deep":    {"raw": int(900 - deep_pct    / 100 * 520), "moisture_percent": round(deep_pct,    2), "_mock": True},
        }

# ─── Battery — Module Sensor Voltage DC 0-25V ────────────────────
class MockBattery(_MockBase):
    PCT_BASE = {"normal": 85.0, "warning": 42.0, "critical": 15.0}

    def read(self) -> dict:
        sc  = self._scenario()
        pct = max(0.0, min(100.0, _jitter(self.PCT_BASE[sc], 0.04)))
        v   = round(9.0 + pct / 100 * 3.6, 2)
        return {"voltage": v, "percent": round(pct, 1), "_mock": True, "_scenario": sc}


# ─── Mock Alarm (no GPIO) ────────────────────────────────────────
class MockAlarmController:
    """Cetak level alarm to console; not sentuh GPIO."""

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

