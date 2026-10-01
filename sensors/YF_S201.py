import time
from gpiozero import DigitalInputDevice
from config import settings

try:
    from gpiozero.pins.lgpio import LGPIOFactory
except ImportError:
    LGPIOFactory = None


class YFS201:
    def __init__(self, GPIO_YF=None):
        # Use configuration GPIO_YF; 16 is fallback for wiring YF-S201.
        self.GPIO_YF = GPIO_YF if GPIO_YF is not None else getattr(settings, "GPIO_YF", 16)
        
        device_options = {
            "pin": self.GPIO_YF,
            "pull_up": False
        }
        
        if LGPIOFactory is not None:
            device_options["pin_factory"] = LGPIOFactory()
            
        self.sensor = DigitalInputDevice(**device_options)
        self.pulse_count = 0
        
        # Register function callback interrupt
        self.sensor.when_activated = self._count_pulse

    def _count_pulse(self):
        self.pulse_count += 1

    def read_flow_rate(self, duration: float = 1.0) -> float:
        """Measure flow rate air inside Liter/Minutes during duration sampling specific."""
        self.pulse_count = 0
        time.sleep(duration)
        
        # Calculate frequency Hz based on duration sampling
        hz = self.pulse_count / duration
        
        # Rumus standar YF-S201: Frequency (Hz) / 7.5 = Liter/Minutes
        flow_rate = hz / 7.5
        return flow_rate

    def close(self):
        self.sensor.close()
