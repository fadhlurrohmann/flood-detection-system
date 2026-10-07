"""
NullSensor — fallback if a physical sensor FAILS to initialise
(not installed, driver missing, port/bus not found at startup).

Purpose: so EFWS can keep running even if one sensor (whichever it is)
is missing, without having to change the payload builder / threshold evaluator
code in main.py at all.

IMPORTANT about data types: all the numeric fields below ALWAYS hold Python
`None` (not the string "None", not an error message). `None` -> JSON `null` and
SQLite `NULL` automatically, so REAL/float columns never receive
text. The error message/reason why the sensor could not be read is ONLY stored in a
separate `"error"` key (a string), and is NEVER mixed into a numeric field.

SENSOR_SCHEMAS registers which fields should exist in each
sensor (exactly the same as the shape the real sensor returns on success), so
NullSensor.read() always returns an identical shape --
with all the keys, just with null contents -- whether accessed through
`.get(...)` or directly via `dict[...]`.
"""

SENSOR_SCHEMAS = {
    "bme280":   {"temperature_c": None, "humidity_percent": None, "pressure_hpa": None},
    "pressure": {"current_ma": None, "depth_m": None, "pressure_bar": None, "fault_open_loop": None},
    "wind":    {"speed_ms": None},
    "battery": {"voltage": None, "percent": None},
}


class NullSensor:
    def __init__(self, name: str, reason: str):
        self.name = name
        self.reason = reason
        self._fields = SENSOR_SCHEMAS.get(name, {})

    def read(self) -> dict:
        # A shallow copy is enough: all field contents are None (immutable) or
        # nested dicts that also only contain None, so it is safe not to mutate them.
        result = dict(self._fields)
        result["error"] = (
            f"sensor '{self.name}' unreadable/not installed: {self.reason}"
        )
        return result


class NullAlarmController:
    """Fallback if the relay/siren fails to initialise — the local alarm becomes a no-op,
    but the level state is still recorded, so the operator knows."""

    current_level = "none"

    def __init__(self, reason: str):
        self.reason = reason

    def set_level(self, level: str):
        self.current_level = level

    def silence(self):
        self.current_level = "none"
