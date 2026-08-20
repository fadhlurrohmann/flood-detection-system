import time
from gpiozero import DigitalInputDevice
from config import settings

try:
    from gpiozero.pins.lgpio import LGPIOFactory
except ImportError:
    LGPIOFactory = None


class YFS201:
    def __init__(self, GPIO_YF=None):
        # Gunakan konfigurasi GPIO_YF; 16 adalah fallback untuk wiring YF-S201.
        self.GPIO_YF = GPIO_YF if GPIO_YF is not None else getattr(settings, "GPIO_YF", 16)
        
        device_options = {
            "pin": self.GPIO_YF,
            "pull_up": False
        }
        
        if LGPIOFactory is not None:
            device_options["pin_factory"] = LGPIOFactory()
            
        self.sensor = DigitalInputDevice(**device_options)
        self.pulse_count = 0
        
        # Daftarkan fungsi callback interupsi
        self.sensor.when_activated = self._count_pulse

    def _count_pulse(self):
        self.pulse_count += 1

    def read_flow_rate(self, duration: float = 1.0) -> float:
        """Mengukur debit air dalam Liter/Menit selama durasi sampling tertentu."""
        self.pulse_count = 0
        time.sleep(duration)
        
        # Menghitung frekuensi Hz berdasarkan durasi sampling
        hz = self.pulse_count / duration
        
        # Rumus standar YF-S201: Frekuensi (Hz) / 7.5 = Liter/Menit
        flow_rate = hz / 7.5
        return flow_rate

    def close(self):
        self.sensor.close()
