import signal
from typing import Optional

from gpiozero import DistanceSensor
from config import settings 

try:
    from gpiozero.pins.lgpio import LGPIOFactory
except ImportError:
    LGPIOFactory = None


class JSN_SR04T:
    def __init__(self, trig=None, echo=None, max_distance=4.5):
        self.trig = trig if trig is not None else settings.GPIO_JSN_TRIG
        self.echo = echo if echo is not None else settings.GPIO_JSN_ECHO

        sensor_options = {
            "echo": self.echo,
            "trigger": self.trig,
            "max_distance": max_distance,
        }
        if LGPIOFactory is not None:
            sensor_options["pin_factory"] = LGPIOFactory()
        self.sensor = DistanceSensor(**sensor_options)

    def read(self, timeout: float = 2.0) -> Optional[float]:
        """Read distance in metres, or return None when no echo is received."""
        previous_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, self._handle_timeout)
        signal.setitimer(signal.ITIMER_REAL, timeout)
        try:
            print(
                f"Reading JSN-SR04T: TRIG={self.trig}, ECHO={self.echo}",
                flush=True,
            )
            distance_m = self.sensor.distance
            print(f"Data sensor received: {distance_m:.3f} m", flush=True)
            return distance_m

        except TimeoutError:
            print(
                f"Timeout: not exists echo inside {timeout:.1f} seconds "
                f"(TRIG={self.trig}, ECHO={self.echo})",
                flush=True,
            )
            return None
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)

    @staticmethod
    def _handle_timeout(signum, frame):
        raise TimeoutError

    def close(self):
        self.sensor.close()


# Backward-compatible name for existing callers.
get_JSN_SR04T = JSN_SR04T