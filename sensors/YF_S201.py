"""YF-S201: continuous pulse counting; totals reset when the process restarts.

Default calibration: 450 pulses/litre. Calibrate against a measured volume.
Use a LLC between the 5V signal and Raspberry Pi GPIO.
"""
import math
import threading
import time
from config import settings

try:
    from gpiozero import DigitalInputDevice
    from gpiozero.pins.lgpio import LGPIOFactory
except ImportError:
    DigitalInputDevice = None
    LGPIOFactory = None


class YFS201:
    def __init__(self, GPIO_YF=None, pulses_per_liter=None):
        # The defualt pin setting is GPIO16.
        self.GPIO_YF = GPIO_YF if GPIO_YF is not None else settings.GPIO_YF
        #the pulse per liter should be calibrated and then set in the settings.. the default is 450 for 1/2 inch and 12 for 2 inch. 
        self.pulses_per_liter = (
            settings.FLOW_PULSES_PER_LITER if pulses_per_liter is None else pulses_per_liter
        )
        if not math.isfinite(self.pulses_per_liter) or self.pulses_per_liter <= 0:
            raise ValueError("pulses_per_liter must be finite and positive")
        if DigitalInputDevice is None:
            raise RuntimeError("Please install gpiozero and lgpio")
        self._lock = threading.Lock()
        self._total_pulses = 0
        self._last_pulses = 0
        self.pulse_count = 0
        self._last_read = time.monotonic()
        options = {"pin": self.GPIO_YF, "pull_up": False}
        if LGPIOFactory is not None:
            options["pin_factory"] = LGPIOFactory()
        self.sensor = DigitalInputDevice(**options)
        self.sensor.when_activated = self._count_pulse

    def _count_pulse(self):
        with self._lock:
            self._total_pulses += 1

    def read(self):
        """Nonblocking average since the previous read (first: since startup)."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_read
            if elapsed <= 0:
                raise RuntimeError("Flow sampling interval must be positive")
            pulses = self._total_pulses - self._last_pulses
            self.pulse_count = pulses
            self._last_pulses = self._total_pulses
            self._last_read = now
            return {
                "flow_lpm": round(pulses / self.pulses_per_liter * 60 / elapsed, 3),
                "total_liters": round(self._total_pulses / self.pulses_per_liter, 4),
                "pulse_count": pulses,
                "sample_duration_sec": elapsed,
            }

    def read_flow_rate(self, duration=3.0):
        """Compatibility helper: wait, then read the average since the last read."""
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("duration must be finite and positive")
        time.sleep(duration)
        return self.read()["flow_lpm"]

    def total_liters(self):
        with self._lock:
            return round(self._total_pulses / self.pulses_per_liter, 4)

    def close(self):
        self.sensor.close()
