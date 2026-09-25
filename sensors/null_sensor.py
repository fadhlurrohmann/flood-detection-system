"""
NullSensor — fallback if physical sensor Failed to initialize
(not installed, driver is unavailable, port/bus not found when startup).

Purpose: so that EFWS can keep running although one sensor (anything that)
none, without having to change code payload builder / threshold evaluator
in main.py at all.

IMPORTANT regarding type data: all field numeric below ALWAYS is Python
`None` (not string "None", not error message). `None` -> JSON `null` and
SQLite `NULL` in a automatically, therefore columns ACTUAL/float never receive
text. Error message/reason why sensor not readable ONLY stored in key
separate `"error"` (of type string), NOT EVER mixed to field numeric.

SENSOR_SCHEMAS lists field what only that should exists in each
sensor (exactly same with shape return sensor original when success), biar
NullSensor.read() always returns shape (shape) that identical --
complete with all key, only its contents null -- either diakses through
`.get(...)` or directly `dict[...]`.
"""

SENSOR_SCHEMAS = {
    "mq2":      {"voltage": None, "ppm": None},
    "mq135":    {"voltage": None, "ppm": None},
    "bme280":   {"temperature_c": None, "humidity_percent": None, "pressure_hpa": None},
    "pressure": {"current_ma": None, "depth_m": None, "pressure_bar": None, "fault_open_loop": None},
    "soil": {
        "surface": {"raw": None, "moisture_percent": None},
        "deep":    {"raw": None, "moisture_percent": None},
    },
    "wind":    {"speed_ms": None},
    "battery": {"voltage": None, "percent": None},
}


class NullSensor:
    def __init__(self, name: str, reason: str):
        self.name = name
        self.reason = reason
        self._fields = SENSOR_SCHEMAS.get(name, {})

    def read(self) -> dict:
        # Copy shallow enough: all content field is None (immutable) or
        # dict nested that also only contains None, therefore safe is not mutated.
        result = dict(self._fields)
        result["error"] = (
            f"sensor '{self.name}' not terbaca/not installed: {self.reason}"
        )
        return result


class NullAlarmController:
    """Fallback if relay/siren failed to initialize — alarm local therefore no-op,
    but status level still recorded, so that operator tahu."""

    current_level = "none"

    def __init__(self, reason: str):
        self.reason = reason

    def set_level(self, level: str):
        self.current_level = level

    def silence(self):
        self.current_level = "none"
