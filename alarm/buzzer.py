"""Optional active-buzzer driver for installations that add one."""
import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None


class Buzzer:
    def __init__(self, pin=22):
        if GPIO is None:
            raise RuntimeError("RPi.GPIO is required to use the optional buzzer")
        self.pin = pin
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.OUT)
        GPIO.output(self.pin, GPIO.LOW)

    def on(self):
        GPIO.output(self.pin, GPIO.HIGH)

    def off(self):
        GPIO.output(self.pin, GPIO.LOW)

    def beep(self, duration=0.2, pause=0.2, times=1):
        for _ in range(times):
            self.on()
            time.sleep(duration)
            self.off()
            time.sleep(pause)
