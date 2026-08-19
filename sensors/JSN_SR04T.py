import time
from gpiozero import DistanceSensor
from config import settings 


class JSN_SR04T:
    def __init__(self, trig=None, echo=None):
        self.trig = trig if trig is not None else settings.GPIO_JSN_TRIG
        self.echo = echo if echo is not None else settings.GPIO_JSN_ECHO

        self.sensor = DistanceSensor(echo=self.echo,trigger=self.trig)
    def read(self) -> float:
        """mengambil data jarak dari sensor"""

        return self.sensor.distance