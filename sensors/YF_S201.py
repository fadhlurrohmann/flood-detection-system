import time
from gpiozero import DigitalInputDevice
from config import settings

try:
    from gpiozero.pins.lgpio import LGPIOFactory
except ImportError:
    LGPIOFactory = None


class YFS201:
    def __init__(self, GPIO_YF=None):
        # Use the GPIO_YF setting; 16 is the fallback for the YF-S201 wiring.
        self.GPIO_YF = GPIO_YF if GPIO_YF is not None else getattr(settings, "GPIO_YF", 16)
        
        device_options = {
            "pin": self.GPIO_YF,
            "pull_up": False
        }
        
        if LGPIOFactory is not None:
            device_options["pin_factory"] = LGPIOFactory()
            
        self.sensor = DigitalInputDevice(**device_options)
        self.pulse_count = 0
        
        # Register the interrupt callback
        self.sensor.when_activated = self._count_pulse

    def _count_pulse(self):
        self.pulse_count += 1

    def read_flow_rate(self, duration: float = 1.0) -> float:
        """Measure the water flow rate in Litres/Minute over a given sampling duration."""
        self.pulse_count = 0
        time.sleep(duration)

        # Compute the frequency in Hz from the sampling duration
        hz = self.pulse_count / duration

        # Standard YF-S201 formula: Frequency (Hz) / 7.5 = Litres/Minute
        flow_rate = hz / 7.5
        return flow_rate

    def close(self):
        self.sensor.close()
