"""Every column in the schema must be fillable. Catches name mismatches and forgotten sensors. Temp DB only."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_manager import DBManager, _SENSOR_COLUMNS

# one entry per sensor section, using the same names main.py uses; give every value a real, non-empty reading
DATA = {
    "bme_sensor":        {"temperature_c": 29.5, "humidity_percent": 63.0, "pressure_hpa": 1008.2},
    "sps_sensor":        {"current_ma": 8.2, "depth_m": 1.1, "pressure_bar": 0.1, "fault_open_loop": False},
    "wind_speed_sensor": {"speed_ms": 2.5},
    "wind_dir_sensor":   {"direction_abbr": "NE"},
    "flow_sensor":       {"flow_lpm": 3.2, "total_liters": 10.5},
    "distance_sensor":   {"distance_m": 0.87},
    "battery_sensor":    {"voltage": 12.1, "percent": 88.0},
    "rainfall_sensor":   {"rainfall_total_mm": 12.5, "rainfall_last_hour_mm": 0.4},
    "aqi_sensor":        {"pm1": 6, "pm25": 8, "pm10": 11, "aqi": 26},
}
PAYLOAD = {"telemetry": [{"rainfall": 0.7}]}
OK_TO_BE_EMPTY = {"sensor_errors"}               # only filled when a sensor fails

db = DBManager(db_path=os.path.join(tempfile.mkdtemp(), "t.db"))
try:
    rid = db.log_reading(DATA, PAYLOAD)
except Exception as e:
    sys.exit(f"FAIL  log_reading crashed: {type(e).__name__}: {e}")
row = dict(db.conn.execute("select * from sensor_readings where id=?", (rid,)).fetchone())
empty = [name for name, _ in _SENSOR_COLUMNS if row.get(name) is None and name not in OK_TO_BE_EMPTY]
for name, _ in _SENSOR_COLUMNS:
    mark = "FAIL" if name in empty else "ok  "
    print(f"  {mark} {name:24s} {row.get(name)!r}")
print("\nRESULT:", "ALL COLUMNS FILLED" if not empty else f"{len(empty)} column(s) never get data: {empty}")
sys.exit(1 if empty else 0)