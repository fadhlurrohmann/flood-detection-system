"""
Driver Relay 5V - relay ini menyambungkan sirine 12V/24V/220V 120dB
(with LED flasher bawaan) ke power supply 12V.
Kebanyakan relay module murah aktif-LOW di pin IN (LOW = energized/closed).
Set active_low=False if module Anda aktif-HIGH.

Kebanyakan relay module (with optocoupler) sudah kompatibel logic 3.3V,
jadi BIASANYA not perlu logic level converter for jalur kontrolnya -
tapi check datasheet relay module Anda for make sure (see docs/Pinout.md).
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
            raise RuntimeError("RPi.GPIO is not available - run ini di Raspberry Pi")
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
