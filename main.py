"""Flood warning runtime: local sensing/alarm, durable uploads, background GPS."""
import json
import logging
import math
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from communication.api_publisher import APIPublisher
from config import settings
from config.threshold_resolver import resolve_active_thresholds
from database.db_manager import DBManager
from sensors.null_sensor import NullAlarmController, NullSensor

logger = logging.getLogger("efws.main")


def _load_sim():
    try:
        from communication.sim_detector import detect_sim
        return detect_sim()
    except Exception:
        logger.exception("SIM unavailable; using configured location")
        return None


def _load_sensors_and_alarm():
    if settings.RUN_MODE == "mock":
        from sensors.mock_sensors import (
            MockAlarmController,
            MockBattery,
            MockDistance,
            MockPressureWater,
            MockRainfall,
            MockWaterflow,
        )
        return {
            "pressure": MockPressureWater(), "rain": MockRainfall(),
            "distance": MockDistance(), "flow": MockWaterflow(),
            "battery": MockBattery(),
        }, MockAlarmController()

    # Import each driver independently: one missing library must not disable
    # the other sensors or prevent local alarms from starting.
    from importlib import import_module
    factories = {
        "pressure": ("sensors.pressure", "PressureWaterSensor"),
        "rain": ("sensors.rainfall", "RainfallSensor"),
        "distance": ("sensors.JSN_SR04T", "JSN_SR04T"),
        "flow": ("sensors.YF_S201", "YFS201"),
        "battery": ("sensors.battery", "BatterySensor"),
    }
    sensors = {}
    for name, (module, class_name) in factories.items():
        sensor = None
        try:
            sensor = getattr(import_module(module), class_name)()
            if name == "rain":
                sensor.initialize()
            sensors[name] = sensor
        except Exception as error:
            if sensor is not None and hasattr(sensor, "close"):
                try:
                    sensor.close()
                except Exception:
                    logger.exception("Failed to close %s after initialization error", name)
            logger.error("Sensor %s unavailable: %s", name, error)
            sensors[name] = NullSensor(name, str(error))
    try:
        from alarm.siren import AlarmController
        alarm = AlarmController()
    except Exception as error:
        logger.error("Local siren unavailable: %s", error)
        alarm = NullAlarmController(str(error))
    return sensors, alarm


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _load_hardcoded_thresholds():
    with open(settings.THRESHOLDS_PATH, encoding="utf-8") as file:
        thresholds = json.load(file)
    for key in ("waterDangerThreshold", "rainfallDangerThreshold"):
        value = thresholds.get(key)
        if not _number(value) or value < 0:
            raise ValueError(f"{key} must be a finite, nonnegative number")
    required = thresholds.get("alarm", {}).get("consecutive_readings_required", 3)
    if isinstance(required, bool) or not isinstance(required, int) or required < 1:
        raise ValueError("consecutive_readings_required must be a positive integer")
    return thresholds


def _exceeds(value, danger, lower_is_worse=False):
    if not _number(value) or not _number(danger):
        return False
    return value <= danger if lower_is_worse else value >= danger


class EFWS:
    def __init__(self):
        self.hardcoded_thresholds = _load_hardcoded_thresholds()
        self.db = DBManager()
        self.api = APIPublisher()
        self.api.command_handler = self._process_commands
        self.sensors, self.alarm = _load_sensors_and_alarm()
        self.sim = None
        self._critical_streak = 0
        self._stop_flag = threading.Event()
        self._upload_event = threading.Event()
        self._last_routine_send = None
        self._threads = []
        self._closed = False
        self._location = {
            "lat": settings.DEVICE_LOCATION["lat"],
            "lon": settings.DEVICE_LOCATION["lon"],
            "source": "config", "fix": False,
        }

    def _flush_queue_loop(self):
        # Only this thread uses the HTTP session. Bundles are already in SQLite.
        try:
            while not self._stop_flag.is_set():
                self._upload_event.clear()
                try:
                    while not self._stop_flag.is_set() and self.api.flush_queue(self.db):
                        pass
                except Exception:
                    logger.exception("Upload worker failed; queued data retained")
                self._upload_event.wait(settings.EFWS_CONNECTIVITY_CHECK_SEC)
        finally:
            self.api.close()

    def _retention_loop(self):
        while not self._stop_flag.is_set():
            try:
                self.db.purge_old_data(settings.DB_RETENTION_DAYS)
            except Exception:
                logger.exception("Database retention failed")
            self._stop_flag.wait(settings.DB_RETENTION_CHECK_SEC)

    def _gps_loop(self):
        try:
            while not self._stop_flag.is_set():
                if self.sim is None:
                    self.sim = _load_sim()
                self._update_gps()
                self._stop_flag.wait(settings.GPS_INTERVAL_SEC)
        finally:
            if self.sim is not None:
                self.sim.close()

    def _update_gps(self):
        if self.sim is None:
            return
        try:
            result = self.sim.get_gps(timeout=settings.GPS_TIMEOUT)
            lat, lon = result.get("lat"), result.get("lon")
            if result.get("fix") and _number(lat) and _number(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
                self._location = {"lat": lat, "lon": lon, "source": "gps", "fix": True}
            else:
                self._location = {**self._location, "fix": False, "source": "last-known/config"}
        except Exception:
            self._location = {**self._location, "fix": False, "source": "last-known/config"}
            logger.exception("GPS failed; retaining last known/configured location")

    def _read_all(self):
        data = {}
        for key, sensor in self.sensors.items():
            try:
                reading = sensor.read()
                if key == "distance" and not isinstance(reading, dict):
                    reading = {"distance_m": reading}
                if not isinstance(reading, dict):
                    raise TypeError("Invalid sensor response")
                if any(isinstance(v, float) and not math.isfinite(v) for v in reading.values()):
                    raise ValueError("Sensor returned a nonfinite value")
                if reading.get("fault_open_loop") or reading.get("fault_out_of_range"):
                    reading = {**reading, "depth_m": None, "pressure_bar": None,
                               "error": "Pressure current loop outside valid measurement range"}
                if key == "distance" and reading.get("distance_m") is None and not reading.get("error"):
                    raise ValueError("No ultrasonic echo")
                data[key] = reading
                if reading.get("error"):
                    logger.warning("Sensor %s: %s", key, reading["error"])
            except Exception as error:
                logger.warning("Sensor %s read failed: %s", key, error)
                data[key] = NullSensor(key, str(error)).read()
        data["_timestamp"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        return data

    def _ultrasonic_depth(self, data):
        distance = data.get("distance", {}).get("distance_m")
        height = settings.ULTRASONIC_MOUNT_HEIGHT_M
        if _number(distance) and _number(height) and 0 <= distance <= height:
            return round(height - distance, 3)
        return None

    def _evaluate(self, data):
        thresholds = resolve_active_thresholds(self.hardcoded_thresholds, self.api.remote_config)
        pressure = data.get("pressure", {})
        pressure_depth = pressure.get("depth_m") if not pressure.get("error") else None
        checks = {
            "water": _exceeds(pressure_depth, thresholds["waterDangerThreshold"]),
            "ultrasonic_water": _exceeds(self._ultrasonic_depth(data), thresholds["waterDangerThreshold"]),
            "rainfall": _exceeds(data.get("rain", {}).get("rainfall_last_hour_mm"),
                                 thresholds["rainfallDangerThreshold"]),
        }
        triggered = [name for name, active in checks.items() if active]
        return bool(triggered), triggered

    def _identity(self):
        return {"deviceId": settings.DEVICE_ID, "deviceToken": settings.DEVICE_TOKEN}

    def _build_location_payload(self):
        location = self._location  # GPS replaces the whole snapshot atomically.
        return {**self._identity(), "latitude": location["lat"], "longitude": location["lon"]}

    def _build_telemetry_payload(self, data):
        pressure = data.get("pressure", {})
        rain = data.get("rain", {})
        flow = data.get("flow", {})
        battery = data.get("battery", {})
        depth = pressure.get("depth_m") if not pressure.get("error") else None
        if depth is None:
            depth = self._ultrasonic_depth(data)
        return {**self._identity(), "telemetry": [{
            "timestamp": data["_timestamp"],
            "waterLevel": depth,
            "waterLevelCurrentMa": pressure.get("current_ma"),
            "distanceM": data.get("distance", {}).get("distance_m"),
            "flowRateLpm": flow.get("flow_lpm"),
            "flowTotalLiters": flow.get("total_liters"),
            "rainfallTotalMm": rain.get("rainfall_total_mm"),
            "rainfallLastHour": rain.get("rainfall_last_hour_mm"),
            "batteryVoltage": battery.get("voltage"),
            "batteryLevel": battery.get("percent"),
        }]}

    def _build_heartbeat_payload(self, data):
        return {**self._identity(), "batteryLevel": data.get("battery", {}).get("percent")}

    def _build_ack_payload(self, command_id, status, error=""):
        return {**self._identity(), "commandId": command_id, "status": status, "error": error}

    def _handle_alarm(self, any_triggered, triggered):
        required = self.hardcoded_thresholds.get("alarm", {}).get("consecutive_readings_required", 3)
        self._critical_streak = min(self._critical_streak + 1, required) if any_triggered else 0
        active = self._critical_streak >= required
        self.alarm.set_level("critical" if active else "none")
        if active:
            logger.warning("Local flood alarm: %s", triggered)

    def _send_bundle(self, data, reason, telemetry_payload=None):
        self.db.queue_bundle([
            (settings.location_endpoint(), self._build_location_payload()),
            (settings.telemetry_endpoint(), telemetry_payload or self._build_telemetry_payload(data)),
            (settings.heartbeat_endpoint(), self._build_heartbeat_payload(data)),
        ])
        self._upload_event.set()
        logger.info("Queued location, telemetry and heartbeat: %s", reason)

    def _process_commands(self, commands):
        for command in commands:
            if not isinstance(command, dict):
                continue
            command_id = command.get("id", "")
            name = command.get("command", "")
            try:
                if name != "Reboot":
                    raise ValueError(f"Unknown command: {name}")
                self._cmd_reboot()
                ack = self._build_ack_payload(command_id, "SUCCESS")
            except Exception as error:
                ack = self._build_ack_payload(command_id, "FAILED", str(error))
            self.db.queue_api(settings.command_ack_endpoint(), ack)
            self._upload_event.set()

    def _cmd_reboot(self):
        if settings.RUN_MODE == "mock":
            logger.info("MOCK Reboot command: service restart simulated")
            return
        delay = max(1, settings.COMMAND_REBOOT_DELAY_SEC)
        # ACK means the service restart was scheduled, not that it completed.
        subprocess.Popen(
            ["bash", "-c", f"sleep {delay} && sudo -n systemctl restart efws.service"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )

    def run_cycle(self):
        data = self._read_all()
        triggered, reasons = self._evaluate(data)
        self._handle_alarm(triggered, reasons)
        telemetry = self._build_telemetry_payload(data)
        self.db.log_reading(data, telemetry)
        now = time.monotonic()
        if triggered or self._last_routine_send is None or now - self._last_routine_send >= settings.ROUTINE_SEND_INTERVAL_SEC:
            self._send_bundle(data, "emergency" if triggered else "routine", telemetry)
            self._last_routine_send = now
        logger.info("READ depth=%s m distance=%s m flow=%s L/min rain_1h=%s mm battery=%s V | triggers=%s",
                    telemetry["telemetry"][0]["waterLevel"], data["distance"].get("distance_m"),
                    data["flow"].get("flow_lpm"), data["rain"].get("rainfall_last_hour_mm"),
                    data["battery"].get("voltage"), reasons)
        return data

    def run(self):
        for target in (self._flush_queue_loop, self._retention_loop, self._gps_loop):
            thread = threading.Thread(target=target, name=target.__name__, daemon=True)
            self._threads.append(thread)
            thread.start()
        try:
            while not self._stop_flag.is_set():
                started = time.monotonic()
                self.run_cycle()
                self._stop_flag.wait(max(0, settings.SENSOR_READ_INTERVAL_SEC - (time.monotonic() - started)))
        except KeyboardInterrupt:
            logger.info("Stopped by user")
        finally:
            self.close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._stop_flag.set()
        self._upload_event.set()
        for resource in [self.alarm, *self.sensors.values()]:
            cleanup = getattr(resource, "close", None) or getattr(resource, "silence", None)
            if cleanup:
                try:
                    cleanup()
                except Exception:
                    logger.exception("Resource cleanup failed")
        for thread in self._threads:
            thread.join(timeout=5)
        if not self._threads:
            self.api.close()
        if not any(t.is_alive() and t.name != "_gps_loop" for t in self._threads):
            self.db.close()
        from sensors.mcp3008 import close_mcp3008
        close_mcp3008()


def main():
    Path(settings.LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(settings.LOG_PATH, encoding="utf-8")])
    app = EFWS()
    signal.signal(signal.SIGTERM, lambda *_: app._stop_flag.set())
    app.run()


if __name__ == "__main__":
    main()
