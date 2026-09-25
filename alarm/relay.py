"""
Driver Relay 5V - relay this connects siren 12V/24V/220V 120dB
(with LED flasher bawaan) to power supply 12V.
Most relay module murah active-LOW in pin IN (LOW = energized/closed).
Set active_low=False if module You active-HIGH.

Most relay module (with optocoupler) already kompatibel logic 3.3V,
therefore USUALLY not needs logic level converter for route control -
but check datasheet relay module You for make sure (see docs/Pinout.md).
"""
from config import settings

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None


class Relay:
    def __init__(self, pin=None, active_low=True):
        self.pin = pin if pin is not None else settings.GPIO_RELAY_SIREN
        self.active_low = active_low
        if GPIO is None:
            raise RuntimeError("RPi.GPIO is not available - run this in Raspberry Pi")
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.OUT)
        self.off()

    def on(self):
        GPIO.output(self.pin, GPIO.LOW if self.active_low else GPIO.HIGH)

    def off(self):
        GPIO.output(self.pin, GPIO.HIGH if self.active_low else GPIO.LOW)

    def is_on(self) -> bool:
        state = GPIO.input(self.pin)
        return (state == GPIO.LOW) if self.active_low else (state == GPIO.HIGH)
