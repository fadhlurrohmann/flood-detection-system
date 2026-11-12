"""JSN-SR04T in trigger/echo mode; bounded reads that reject stale echoes."""
import math
import threading
from typing import Optional

from gpiozero import DistanceSensor

from config import settings

try:
    from gpiozero.pins.lgpio import LGPIOFactory
except ImportError:
    LGPIOFactory = None


class _FreshDistanceSensor(DistanceSensor):
    """Expose each completed GPIO Zero sample, including failed echoes.

    GPIO Zero's normal averaging queue ignores missing echoes and can keep an
    old distance indefinitely. A new sample event prevents that stale reading
    from being interpreted as a current water measurement.
    """
    def __init__(self, **kwargs):
        self.sample_ready = threading.Event()
        self.sample_lock = threading.Lock()
        self.sample = None
        super().__init__(**kwargs)

    def _read(self):
        value = super()._read()
        with self.sample_lock:
            self.sample = value
            self.sample_ready.set()
        return value


class JSN_SR04T:
    def __init__(self, trig=None, echo=None, max_distance=None):
        self.trig = trig if trig is not None else settings.GPIO_JSN_TRIG
        self.echo = echo if echo is not None else settings.GPIO_JSN_ECHO

        sensor_options = {
            "echo": self.echo,
            "trigger": self.trig,
            "max_distance": settings.JSN_MAX_DISTANCE_M if max_distance is None else max_distance,
            "queue_len": 1,
            "partial": True,
        }
        self._factory = None
        if LGPIOFactory is not None:
            self._factory = LGPIOFactory()
            sensor_options["pin_factory"] = self._factory
        try:
            self.sensor = _FreshDistanceSensor(**sensor_options)
        except Exception:
            if self._factory is not None:
                self._factory.close()
            raise

    def read(self, timeout: float = 2.0) -> Optional[float]:
        """Read distance in metres, or return None when no echo is received."""
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        self.sensor.sample_ready.clear()
        if not self.sensor.sample_ready.wait(timeout):
            return None
        with self.sensor.sample_lock:
            value = self.sensor.sample
        if value is None or not math.isfinite(value) or not 0 < value < 1:
            return None
        return round(value * self.sensor.max_distance, 4)

    def close(self):
        self.sensor.close()
        if self._factory is not None:
            self._factory.close()


# Backward-compatible name for existing callers.
get_JSN_SR04T = JSN_SR04T
