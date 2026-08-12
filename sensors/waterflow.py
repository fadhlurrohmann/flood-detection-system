"""
YF-S201 Water Flow Sensor driver.

Wiring:
    Red (VCC)    -> 5V
    Black (GND)  -> GND
    Yellow (sig) -> voltage divider / LLC (5V -> 3.3V) -> GPIO pin
"""

import time
import threading

from config import settings

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None


class FlowSensor:

    def __init__(self, pin=None, pulses_per_liter=None):
        if GPIO is None:
            raise RuntimeError("Please install RPi.GPIO: pip install RPi.GPIO")

        self.pin = pin or getattr(settings, "FLOW_SENSOR_PIN", 17)
        self.pulses_per_liter = pulses_per_liter or getattr(settings, "FLOW_PULSES_PER_LITER", 450)

        self._pulse_count = 0
        self._total_pulses = 0
        self._lock = threading.Lock()

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(self.pin, GPIO.FALLING, callback=self._on_pulse)

    def _on_pulse(self, channel):
        with self._lock:
            self._pulse_count += 1
            self._total_pulses += 1

    def read_flow_rate(self, window_sec=1.0):
        """Blocking — measures pulses over window_sec, returns L/min."""
        with self._lock:
            self._pulse_count = 0
        time.sleep(window_sec)
        with self._lock:
            pulses = self._pulse_count

        liters = pulses / self.pulses_per_liter
        return round((liters / window_sec) * 60.0, 3)

    def total_liters(self):
        with self._lock:
            pulses = self._total_pulses
        return round(pulses / self.pulses_per_liter, 4)

    def read(self):
        return {
            "flow_lpm": self.read_flow_rate(),
            "total_liters": self.total_liters(),
        }

    def close(self):
        GPIO.remove_event_detect(self.pin)
        GPIO.cleanup(self.pin)