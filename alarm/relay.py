"""
5V relay driver - this relay connects the 12V/24V/220V 120dB siren
(with built-in LED flasher) to the 12V power source.
Most cheap relay modules are active-LOW on the IN pin (LOW = energized/closed).
Set active_low=False if your module is active-HIGH.

Most relay modules (with an optocoupler) are already 3.3V logic compatible,
so a logic level converter is USUALLY not needed for the control line -
but check your relay module's datasheet to be sure (see docs/Pinout.md).
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
            raise RuntimeError("RPi.GPIO is not available - run this on a Raspberry Pi")
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
