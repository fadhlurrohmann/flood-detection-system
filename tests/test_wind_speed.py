"""Unit tests for the Modbus wind-speed sensor driver."""

import unittest
from unittest.mock import patch

from sensors.wind_speed import WindSpeedSensor


class FakeSerial:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeInstrument:
    def __init__(self, register_value):
        self.serial = FakeSerial()
        self.register_value = register_value
        self.clear_buffers_before_each_transaction = False
        self.read_register_call = None

    def read_register(self, *args, **kwargs):
        self.read_register_call = (args, kwargs)
        return self.register_value


class WindSpeedSensorTests(unittest.TestCase):
    def test_read_converts_register_value_to_metres_per_second(self):
        instrument = FakeInstrument(123)
        with (
            patch("sensors.wind_speed.settings.ANEMOMETER_SPEED_REGISTER", 7),
            patch("sensors.wind_speed.settings.ANEMOMETER_FUNCTION_CODE", 4),
            patch("sensors.wind_speed.settings.ANEMOMETER_SPEED_SCALE", 0.1),
        ):
            sensor = WindSpeedSensor(instrument=instrument)
            self.assertEqual(sensor.read(), {"speed_ms": 12.3})

        self.assertEqual(instrument.mode, "rtu")
        self.assertEqual(
            instrument.read_register_call,
            ((7,), {
                "number_of_decimals": 0,
                "functioncode": 4,
                "signed": False,
            }),
        )

    def test_close_releases_serial_port(self):
        instrument = FakeInstrument(0)
        sensor = WindSpeedSensor(instrument=instrument)

        sensor.close()

        self.assertTrue(instrument.serial.closed)


if __name__ == "__main__":
    unittest.main()
