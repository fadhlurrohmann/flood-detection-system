"""
NullSensor — fallback if physical sensor Failed to initialize
(not installed, driver none, port/bus not ketemu when startup).

Tujuan: so that EFWS tetap bisa jalan walau wrong satu sensor (apapun itu)
none, without harus mengubah kode payload builder / threshold evaluator
di main.py sama sekali.

PENTING soal tipe data: all field numerik di bawah SELALU bernilai Python
`None` (not string "None", not error message). `None` -> JSON `null` dan
SQLite `NULL` secara otomatis, jadi columns REAL/float not pernah receiving
text. Error message/reason kenapa sensor not readable ONLY disimpan di key
separate `"error"` (bertipe string), TIDAK PERNAH dicampur ke field angka.

SENSOR_SCHEMAS mendaftarkan field apa saja that harusnya ada di each
sensor (persis sama with bentuk return sensor aslinya when sukses), biar
NullSensor.read() selalu mengembalikan bentuk (shape) that identik --
lengkap with all key, only isinya null -- baik diakses through
`.get(...)` maupun directly `dict[...]`.
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
        # Copy dangkal cukup: all content field adalah None (immutable) or
        # dict nested that juga only contains None, jadi safe not dimutasi.
        result = dict(self._fields)
        result["error"] = (
            f"sensor '{self.name}' tidak terbaca/tidak terpasang: {self.reason}"
        )
        return result


class NullAlarmController:
    """Fallback if relay/sirine failed to initialize — alarm local jadi no-op,
    tapi status level tetap dicatat, so that operator tahu."""

    current_level = "none"

    def __init__(self, reason: str):
        self.reason = reason

    def set_level(self, level: str):
        self.current_level = level

    def silence(self):
        self.current_level = "none"
