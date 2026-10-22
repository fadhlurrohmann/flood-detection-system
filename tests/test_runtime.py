"""Hardware-free regression suite: python -m unittest discover -s tests -p test_runtime.py -v"""
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["EFWS_API_URL"] = "http://127.0.0.1:1/test"
os.environ["EFWS_RUN_MODE"] = "mock"

from communication.api_publisher import APIPublisher
from config import settings
from config.threshold_resolver import resolve_active_thresholds
from database.db_manager import DBManager
from main import EFWS, _load_sensors_and_alarm
from sensors.battery import BatterySensor
from sensors.null_sensor import NullSensor
from sensors.pressure import PressureWaterSensor
from sensors.rainfall import RainfallSensor
from sensors.YF_S201 import YFS201


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config_patch = patch.multiple(settings, RUN_MODE="mock",
            DB_PATH=str(Path(self.temp.name) / "runtime.db"), ULTRASONIC_MOUNT_HEIGHT_M=None)
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        # DBManager's default path is bound at import; explicitly inject it.
        with patch("main.DBManager", side_effect=lambda: DBManager(settings.DB_PATH)):
            self.app = EFWS()
        self.addCleanup(self.app.close)
        self.data = {
            "pressure": {"depth_m": 0.2, "current_ma": 5.067, "pressure_bar": 0.0196,
                         "fault_open_loop": False},
            "distance": {"distance_m": 2.8},
            "rain": {"rainfall_total_mm": 200, "rainfall_last_hour_mm": 0.5,
                     "working_time_hours": 24},
            "flow": {"flow_lpm": 5.5, "total_liters": 25},
            "battery": {"voltage": 12, "percent": 83.3},
            "_timestamp": "2026-10-21T00:00:00.000Z",
        }

    def set_readings(self, data):
        self.app.sensors = {name: Mock(read=Mock(return_value=value)) for name, value in data.items()
                            if not name.startswith("_")}

    def test_exact_sensor_set_in_mock_mode(self):
        self.assertEqual(set(self.app.sensors), {"pressure", "distance", "flow", "battery", "rain"})
        data = self.app._read_all()
        self.assertTrue(all(not v.get("error") for v in data.values() if isinstance(v, dict)))
        self.assertIsInstance(data["distance"]["distance_m"], float)

    def test_high_water_at_threshold_and_low_water_normal(self):
        self.assertEqual(self.app._evaluate(self.data), (False, []))
        self.data["pressure"]["depth_m"] = 0.5
        self.assertEqual(self.app._evaluate(self.data), (True, ["water"]))

    def test_hourly_rain_triggers_but_lifetime_total_does_not(self):
        self.assertFalse(self.app._evaluate(self.data)[0])
        self.data["rain"]["rainfall_last_hour_mm"] = 30
        self.assertEqual(self.app._evaluate(self.data), (True, ["rainfall"]))

    def test_remote_threshold_validation_and_per_field_fallback(self):
        local = self.app.hardcoded_thresholds
        for bad in (None, "bad", float("nan"), float("inf"), -1, True):
            with self.subTest(bad=bad):
                resolved = resolve_active_thresholds(local, {"waterDangerThreshold": bad,
                    "rainfallDangerThreshold": 40})
                self.assertEqual(resolved["waterDangerThreshold"], 0.5)
                self.assertEqual(resolved["rainfallDangerThreshold"], 40)
        self.app.api.remote_config = {"waterDangerThreshold": 0.1}
        self.assertTrue(self.app._evaluate(self.data)[0])

    def test_siren_requires_consecutive_readings_then_turns_off(self):
        for _ in range(2):
            self.app._handle_alarm(True, ["water"])
            self.assertEqual(self.app.alarm.current_level, "none")
        self.app._handle_alarm(True, ["water"])
        self.assertEqual(self.app.alarm.current_level, "critical")
        self.app._handle_alarm(False, [])
        self.assertEqual(self.app.alarm.current_level, "none")
        self.app._handle_alarm(True, ["water"])
        self.assertEqual(self.app.alarm.current_level, "none")

    def test_calibrated_ultrasonic_detects_flood_and_falls_back_for_telemetry(self):
        with patch.object(settings, "ULTRASONIC_MOUNT_HEIGHT_M", 3):
            self.data["distance"]["distance_m"] = 2
            self.data["pressure"] = NullSensor("pressure", "disconnected").read()
            self.assertEqual(self.app._evaluate(self.data), (True, ["ultrasonic_water"]))
            self.assertEqual(self.app._build_telemetry_payload(self.data)["telemetry"][0]["waterLevel"], 1)
        self.assertFalse(self.app._evaluate(self.data)[0])

    def test_sensor_failures_are_null_and_do_not_crash(self):
        self.app.sensors = {name: Mock(read=Mock(side_effect=OSError("unplugged")))
                            for name in ("pressure", "rain", "distance", "flow", "battery")}
        data = self.app._read_all()
        self.assertFalse(self.app._evaluate(data)[0])
        payload = self.app._build_telemetry_payload(data)["telemetry"][0]
        self.assertTrue(all(v is None for k, v in payload.items() if k != "timestamp"))
        self.app.db.log_reading(data, self.app._build_telemetry_payload(data))
        self.assertIsNone(self.app.db.recent_readings()[0]["water_fault_open"])

    def test_pressure_fault_and_nan_are_not_valid_measurements(self):
        self.data["pressure"].update(depth_m=3, fault_open_loop=True)
        self.data["flow"]["flow_lpm"] = float("nan")
        self.set_readings(self.data)
        data = self.app._read_all()
        self.assertIsNone(data["pressure"]["depth_m"])
        self.assertIsNone(data["flow"]["flow_lpm"])
        self.assertFalse(self.app._evaluate(data)[0])
        json.dumps(self.app._build_telemetry_payload(data), allow_nan=False)

    def test_payload_contains_all_current_sensors_and_utc_timestamp(self):
        payload = self.app._build_telemetry_payload(self.data)
        row = payload["telemetry"][0]
        self.assertEqual(row["timestamp"], self.data["_timestamp"])
        self.assertEqual(row["distanceM"], 2.8)
        self.assertEqual(row["rainfallLastHour"], 0.5)
        self.assertEqual(row["batteryVoltage"], 12)
        self.assertEqual(row["flowRateLpm"], 5.5)
        self.assertEqual(self.app._build_heartbeat_payload(self.data)["batteryLevel"], 83.3)
        self.assertTrue(set(row).isdisjoint({"soilMoisture", "temp", "humidity", "windSpeed", "flameDetected"}))

    def test_every_cycle_logged_and_only_due_cycles_queued(self):
        self.set_readings(self.data)
        self.app.run_cycle()
        self.app.run_cycle()
        self.assertEqual(len(self.app.db.recent_readings()), 2)
        self.assertEqual(self.app.db.count_pending_queue(), 3)
        self.data["pressure"]["depth_m"] = 0.8
        self.app.run_cycle()
        self.assertEqual(self.app.db.count_pending_queue(), 6)

    def test_queue_persists_exact_payload_after_restart_and_flush(self):
        payload = self.app._build_telemetry_payload(self.data)
        path = str(Path(self.temp.name) / "restart.db")
        db = DBManager(path)
        db.queue_api(settings.telemetry_endpoint(), payload)
        db.close()
        db = DBManager(path)
        self.addCleanup(db.close)
        api = APIPublisher()
        self.addCleanup(api.close)
        api.online = True
        with patch.object(api, "_post_once", return_value=(False, None, None, True)):
            api.flush_queue(db)
        self.assertEqual(db.count_pending_queue(), 1)
        self.assertEqual(json.loads(db.get_pending_queue()[0]["payload"]), payload)
        with patch.object(api, "_post_once", return_value=(True, 200, {"config": {"waterDangerThreshold": 1}}, False)) as post:
            self.assertEqual(api.flush_queue(db), 1)
            self.assertEqual(json.loads(post.call_args.args[1]), payload)
        self.assertEqual(db.count_pending_queue(), 0)
        self.assertEqual(api.remote_config["waterDangerThreshold"], 1)

    def test_queued_heartbeat_commands_are_executed_and_acknowledged(self):
        self.app.db.queue_api(settings.heartbeat_endpoint(), self.app._build_heartbeat_payload(self.data))
        self.app.api.online = True
        with patch.object(self.app.api, "_post_once", return_value=(True, 200,
            {"commands": [{"id": "abc", "command": "Reboot"}]}, False)), patch("main.subprocess.Popen") as popen:
            self.app.api.flush_queue(self.app.db)
            popen.assert_not_called()
        ack = json.loads(self.app.db.get_pending_queue()[0]["payload"])
        self.assertEqual((ack["commandId"], ack["status"]), ("abc", "SUCCESS"))

    def test_rejected_queue_item_is_not_retried(self):
        self.app.db.queue_api(settings.telemetry_endpoint(), {"bad": 1})
        self.app.api.online = True
        with patch.object(self.app.api, "_post_once", return_value=(False, 422, {}, False)) as post:
            self.app.api.flush_queue(self.app.db)
            self.app.api.flush_queue(self.app.db)
            self.assertEqual(post.call_count, 1)
        self.assertEqual(self.app.db.count_pending_queue(), 0)

    def test_old_schema_migrates_preserves_rows_and_records_new_fields(self):
        path = str(Path(self.temp.name) / "old.db")
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE sensor_readings (id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, "
                "device_id TEXT NOT NULL, water_current_ma REAL, water_depth_m REAL, water_fault_open INTEGER, "
                "rainfall_mm REAL, rain_working_hrs REAL, full_payload TEXT, soil_legacy REAL)")
            conn.execute("INSERT INTO sensor_readings (timestamp, device_id, soil_legacy) VALUES ('2020', 'old', 9)")
        conn.close()
        db = DBManager(path)
        self.addCleanup(db.close)
        db.log_reading(self.data, self.app._build_telemetry_payload(self.data))
        rows = db.conn.execute("SELECT * FROM sensor_readings ORDER BY id").fetchall()
        self.assertEqual(rows[0]["soil_legacy"], 9)
        self.assertEqual(rows[1]["rainfall_last_hour_mm"], 0.5)
        self.assertEqual(rows[1]["rain_working_hrs"], 24)
        self.assertEqual(rows[1]["battery_voltage"], 12)
        self.assertEqual(rows[1]["flow_total_liters"], 25)

    def test_concurrent_logging_queue_and_retention(self):
        errors = []
        def work():
            try:
                for _ in range(20):
                    self.app.db.log_reading(self.data, self.app._build_telemetry_payload(self.data))
                    self.app.db.queue_api("test", {"value": 1})
                    self.app.db.purge_old_data(9999)
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=work) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertEqual(errors, [])
        self.assertEqual(self.app.db.count_pending_queue(), 60)

    def test_missing_hardware_libraries_do_not_abort_factory(self):
        with patch.object(settings, "RUN_MODE", "hardware"), patch("importlib.import_module", side_effect=ImportError("missing")):
            sensors, alarm = _load_sensors_and_alarm()
        self.assertEqual(set(sensors), set(self.app.sensors))
        self.assertTrue(all(isinstance(s, NullSensor) for s in sensors.values()))
        alarm.silence()

    def test_pressure_single_sample_and_open_loop(self):
        adc = Mock()
        with patch("sensors.pressure.get_mcp3008", return_value=adc):
            sensor = PressureWaterSensor()
        adc.read_raw.return_value = 310
        result = sensor.read()
        self.assertEqual(adc.read_raw.call_count, 1)
        self.assertAlmostEqual(result["depth_m"], 1.125, delta=0.01)
        adc.read_raw.return_value = 0
        result = sensor.read()
        self.assertTrue(result["fault_open_loop"])
        self.assertIsNone(result["depth_m"])

    def test_battery_scaling_and_invalid_calibration(self):
        with patch("sensors.battery.get_mcp3008", return_value=Mock(read_raw=Mock(return_value=744))):
            sensor = BatterySensor()
            reading = sensor.read()
            self.assertAlmostEqual(reading["voltage"], 12, delta=0.01)
            self.assertTrue(0 <= reading["percent"] <= 100)
            with self.assertRaises(ValueError):
                BatterySensor(batt_min_v=12, batt_max_v=12)

    def test_rain_initializes_identity_and_hour_window_once(self):
        sensor = RainfallSensor.__new__(RainfallSensor)
        sensor._initialized = False
        with (patch.object(sensor, "begin", return_value=True), patch.object(sensor, "set_rainfall_window") as window,
            patch.object(sensor, "rainfall_total", return_value=20), patch.object(sensor, "window_rainfall", return_value=5),
            patch.object(sensor, "raw_tip_count", return_value=10), patch.object(sensor, "working_time_hours", return_value=24)):
            self.assertEqual(sensor.read()["rainfall_last_hour_mm"], 5)
            sensor.read()
            window.assert_called_once_with(1)

    def test_flow_counts_continuously_between_reads(self):
        clock = Mock(return_value=0)
        with (patch("sensors.YF_S201.DigitalInputDevice", return_value=Mock()), patch("sensors.YF_S201.LGPIOFactory", None),
            patch("sensors.YF_S201.time.monotonic", clock)):
            sensor = YFS201(pulses_per_liter=450)
            self.addCleanup(sensor.close)
            for _ in range(450):
                sensor._count_pulse()
            clock.return_value = 60
            self.assertEqual(sensor.read()["flow_lpm"], 1)
            clock.return_value = 120
            reading = sensor.read()
            self.assertEqual(reading["flow_lpm"], 0)
            self.assertEqual(reading["total_liters"], 1)

    def test_live_workers_deliver_http_and_stop_cleanly(self):
        received = []
        heartbeat = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                received.append((self.path, body))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"config":{"waterDangerThreshold":0.9}}')
                if self.path.endswith("heartbeat"):
                    heartbeat.set()

            def log_message(self, *_):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        self.set_readings(self.data)
        with (patch.dict(os.environ, {"EFWS_API_URL": base_url}),
              patch.multiple(settings, API_BASE_URL=base_url, SENSOR_READ_INTERVAL_SEC=0.05),
              patch("main._load_sim", return_value=None)):
            loop = threading.Thread(target=self.app.run)
            loop.start()
            try:
                self.assertTrue(heartbeat.wait(5), "No complete HTTP bundle received")
                self.assertEqual([p for p, _ in received[:3]],
                                 ["/sensors/location", "/sensors/telemetry", "/sensors/heartbeat"])
                self.assertEqual(received[1][1]["telemetry"][0]["batteryVoltage"], 12)
            finally:
                self.app._stop_flag.set()
                self.app._upload_event.set()
                loop.join(10)
                server.shutdown()
                server.server_close()
                server_thread.join(2)
        self.assertFalse(loop.is_alive())
        self.assertTrue(all(not thread.is_alive() for thread in self.app._threads))
        self.assertEqual(self.app.api.remote_config["waterDangerThreshold"], 0.9)

    def test_blocked_http_does_not_block_sensor_cycles_or_local_alarm(self):
        entered = threading.Event()
        release = threading.Event()
        def slow_post(*_):
            entered.set()
            release.wait(3)
            return False, None, None, True

        self.data["pressure"]["depth_m"] = 1
        self.set_readings(self.data)
        self.app.api.online = True
        self.app._send_bundle(self.data, "test")
        worker = threading.Thread(target=self.app._flush_queue_loop)
        with patch.object(self.app.api, "_post_once", side_effect=slow_post):
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                for _ in range(3):
                    self.app.run_cycle()
                self.assertFalse(release.is_set())
                self.assertEqual(self.app.alarm.current_level, "critical")
                self.assertEqual(len(self.app.db.recent_readings()), 3)
            finally:
                self.app._stop_flag.set()
                release.set()
                self.app._upload_event.set()
                worker.join(5)
        self.assertFalse(worker.is_alive())

    def test_retention_preserves_old_pending_uploads(self):
        self.app.db.queue_api("test", {"reading": 1})
        self.app.db.conn.execute("UPDATE api_queue SET timestamp='2000-01-01T00:00:00+00:00'")
        self.app.db.conn.commit()
        self.app.db.purge_old_data(3)
        self.assertEqual(self.app.db.count_pending_queue(), 1)

    def test_rain_bus_failure_keeps_original_oserror_after_retries(self):
        sensor = RainfallSensor.__new__(RainfallSensor)
        sensor.address = 0x1D
        sensor.bus = Mock(i2c_rdwr=Mock(side_effect=OSError(121, "I2C device unavailable")))
        with patch("sensors.rainfall.smbus2", Mock()), patch("sensors.rainfall.time.sleep"):
            with self.assertRaises(OSError) as error:
                sensor._read(0, 4)
            self.assertEqual(error.exception.errno, 121)
            self.assertEqual(sensor.bus.i2c_rdwr.call_count, 3)

    def test_ultrasonic_no_echo_never_reuses_previous_good_distance(self):
        # Exercise fresh/failed echo handling without requiring a GPIO backend.
        class DistanceBase:
            def __init__(self, **options):
                self.max_distance = options["max_distance"]
                self.next_sample = 0.5

            def _read(self):
                return self.next_sample

            def close(self):
                pass

        spec = importlib.util.spec_from_file_location("ultrasonic_test_driver",
            Path(__file__).resolve().parents[1] / "sensors" / "JSN_SR04T.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"gpiozero": SimpleNamespace(DistanceSensor=DistanceBase)}):
            spec.loader.exec_module(module)
        sensor = module.JSN_SR04T()
        self.addCleanup(sensor.close)
        sensor.sensor._read()  # A previous successful echo is present.
        sensor.sensor.next_sample = None
        failed_echo = threading.Timer(0.01, sensor.sensor._read)
        failed_echo.start()
        self.assertIsNone(sensor.read(timeout=0.5))
        failed_echo.join()
        self.assertIsNone(sensor.read(timeout=0.01))  # No new sample at all.
        sensor.sensor.next_sample = 0.5
        good_echo = threading.Timer(0.01, sensor.sensor._read)
        good_echo.start()
        self.assertEqual(sensor.read(timeout=0.5), 2.25)
        good_echo.join()


if __name__ == "__main__":
    unittest.main()
