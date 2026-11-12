"""Hardware-free AQI driver and integration tests."""
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("EFWS_API_URL", "http://127.0.0.1:1/test")

from config import settings
from main import _load_sensors_and_alarm
from sensors import aqi
from sensors.mock_sensors import MockAQI


class AQIRuntimeTests(unittest.TestCase):
    def make_sensor(self, **kwargs):
        bus = Mock()
        bus_patch = patch.object(aqi, "SMBus", return_value=bus)
        bus_patch.start()
        self.addCleanup(bus_patch.stop)
        version_patch = patch.object(aqi, "read_reg", return_value=[7])
        version_patch.start()
        self.addCleanup(version_patch.stop)
        sensor = aqi.AQISensor(**kwargs)
        self.addCleanup(sensor.close)
        return sensor, bus

    def test_warmup_does_not_sleep_or_read_until_ready(self):
        clock = Mock(return_value=0)
        with patch.object(aqi.time, "monotonic", clock), patch.object(aqi.time, "sleep") as sleep:
            sensor, _ = self.make_sensor(window_s=100, warmup_s=30)
            with patch.object(aqi, "read_pm", return_value={"pm1": 6, "pm25": 8, "pm10": 11}) as read:
                with self.assertRaisesRegex(RuntimeError, "warming up"):
                    sensor.read()
                read.assert_not_called()
                clock.return_value = 30
                self.assertEqual(sensor.read(), {"pm1": 6, "pm25": 8, "pm10": 11, "aqi": 26, "provisional": True})
                clock.return_value = 131
                self.assertFalse(sensor.read()["provisional"])
            sleep.assert_not_called()

    def test_read_uses_rolling_mean_instead_of_only_latest_pm(self):
        sensor, _ = self.make_sensor(warmup_s=0)
        with patch.object(aqi, "read_pm", side_effect=[
            {"pm1": 6, "pm25": 8, "pm10": 11},
            {"pm1": 60, "pm25": 100, "pm10": 150},
        ]):
            self.assertEqual(sensor.read()["aqi"], 26)
            reading = sensor.read()
        instantaneous, _, _ = aqi.ispu(100, 150)
        self.assertLess(reading["aqi"], instantaneous)
        self.assertGreater(reading["aqi"], 26)

    def test_failed_initialization_closes_i2c_bus(self):
        bus = Mock()
        with patch.object(aqi, "SMBus", return_value=bus), \
             patch.object(aqi, "read_reg", side_effect=OSError("no sensor")):
            with self.assertRaises(OSError):
                aqi.AQISensor()
        bus.close.assert_called_once()

    def test_i2c_failure_is_raised_instead_of_returning_stale_aqi(self):
        sensor, _ = self.make_sensor(warmup_s=0)
        with patch.object(aqi, "read_pm", side_effect=[
            {"pm1": 6, "pm25": 8, "pm10": 11}, OSError("I2C disconnected")
        ]):
            self.assertEqual(sensor.read()["aqi"], 26)
            with self.assertRaises(OSError):
                sensor.read()

    def test_invalid_measurements_never_enter_the_averages(self):
        sensor, _ = self.make_sensor(warmup_s=0)
        for bad in (float("nan"), float("inf"), -1, 0x8001, True):
            with self.subTest(bad=bad), patch.object(aqi, "read_pm", return_value={"pm1": 6, "pm25": bad, "pm10": 11}):
                with self.assertRaises(ValueError):
                    sensor.read()
                self.assertIsNone(sensor._avg25.mean())

    def test_configured_address_bus_and_optional_wake(self):
        with patch.multiple(settings, I2C_BUS=2, AQI_I2C_ADDRESS=0x18, AQI_WAKE=True):
            sensor, bus = self.make_sensor(warmup_s=0)
            aqi.SMBus.assert_called_once_with(2)
            aqi.read_reg.assert_called_once_with(bus, 0x18, aqi.REG_VERSION, 1)
            bus.write_i2c_block_data.assert_called_once_with(0x18, aqi.REG_POWER, [0x02])

    def test_invalid_window_or_warmup_rejected_before_opening_bus(self):
        for options in ({"window_s": 0}, {"window_s": float("nan")}, {"warmup_s": -1}, {"warmup_s": float("inf")}):
            with self.subTest(options=options), patch.object(aqi, "SMBus") as bus:
                with self.assertRaises(ValueError):
                    aqi.AQISensor(**options)
                bus.assert_not_called()

    def test_mock_has_realistic_ordered_pm_and_same_index_calculation(self):
        with patch("sensors.mock_sensors._jitter", side_effect=lambda value: value):
            sensor = MockAQI()
            with patch.object(sensor, "_scenario", return_value="normal"):
                reading = sensor.read()
        self.assertLessEqual(reading["pm1"], reading["pm25"])
        self.assertLessEqual(reading["pm25"], reading["pm10"])
        self.assertEqual(reading["aqi"], 26)
        self.assertTrue(reading["provisional"])

    def test_hardware_factory_loads_aqi_independently_of_other_drivers(self):
        sensor = Mock()
        constructor = Mock(return_value=sensor)

        def load(module):
            if module == "sensors.aqi":
                return SimpleNamespace(AQISensor=constructor)
            raise ImportError("unavailable")

        with patch.object(settings, "RUN_MODE", "hardware"), patch("importlib.import_module", side_effect=load):
            sensors, alarm = _load_sensors_and_alarm()
        self.assertIs(sensors["aqi"], sensor)
        self.assertEqual(len(sensors), 9)
        constructor.assert_called_once_with()
        alarm.silence()


if __name__ == "__main__":
    unittest.main()
