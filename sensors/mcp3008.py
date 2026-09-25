"""
Driver MCP3008 (ADC 8-channel, 10-bit, via SPI) — menggantikan ADS1115.

MCP3008 used because Pi 4 not punya pin analog. All sensor analog
(MQ-2, MQ-135, soil moisture x2, pressure sensor, battery voltage sensor)
connected ke satu chip MCP3008 that sama, dibaca through SPI hardware (SPI0, CE0).

PENTING soal voltage:
  - MCP3008 VDD/VREF harus 3.3V (NOT 5V) because connected directly ke
    Pi without level shifter di sisi SPI.
  - Tapi MQ-2/MQ-135/soil probe/battery sensor outputnya 0-5V → SETIAP
    channel analog MCP3008 that receiving signal from sensor 5V WAJIB
    melewati logic level converter (sisi HV=5V ke sensor, sisi LV=3.3V ke
    MCP3008), if not pembacaan akan clipping/jenuh di ~3.3V dan bisa
    merusak chip dalam jangka panjang.

Pemetaan channel default (see docs/Pinout.md for detail wiring):
  CH0 → MQ-2 (through LLC)
  CH1 → MQ-135 (through LLC)
  CH2 → Soil moisture — surface (through LLC)
  CH3 → Soil moisture — deep (through LLC)
  CH4 → Submersible pressure sensor, via burden resistor (through LLC)
  CH5 → Battery voltage sensor module (through LLC)
  CH6-CH7 → backup/ekspansi

Requires: pip install spidev
"""
import logging
from config import settings

logger = logging.getLogger("efws.mcp3008")

try:
    import spidev
except ImportError:
    spidev = None


class MCP3008:
    """Satu instance merepresentasikan satu chip MCP3008 physical di SPI0/CE0."""

    def __init__(self, bus=None, device=None, max_speed_hz=None, vref=None):
        if spidev is None:
            raise RuntimeError("spidev is not installed - pip install spidev")

        self.bus = bus if bus is not None else settings.SPI_BUS
        self.device = device if device is not None else settings.SPI_DEVICE
        self.vref = vref if vref is not None else settings.MCP3008_VREF

        self.spi = spidev.SpiDev()
        self.spi.open(self.bus, self.device)
        self.spi.max_speed_hz = max_speed_hz or settings.SPI_MAX_SPEED_HZ
        self.spi.mode = 0b00

    def read_raw(self, channel: int) -> int:
        """Read channel 0-7, return raw value 0-1023 (10-bit)."""
        if not 0 <= channel <= 7:
            raise ValueError("MCP3008 channel harus 0-7")
        cmd = [1, (8 + channel) << 4, 0]
        resp = self.spi.xfzer2(cmd)
        value = ((resp[1] & 3) << 8) + resp[2]
        return value

    def read_voltage(self, channel: int) -> float:
        raw = self.read_raw(channel)
        return round(raw / 1023.0 * self.vref, 4)

    def close(self):
        self.spi.close()


# ─── Singleton helper ──────────────────────────────────────────────
# All sensor analog berbagi SATU chip MCP3008 physical that sama, jadi
# all sensor sebaiknya use instance SPI that sama, not masing-
# masing buka connection SPI sendiri-sendiri.
_instance = None


def get_mcp3008() -> "MCP3008":
    global _instance
    if _instance is None:
        _instance = MCP3008()
    return _instance


if __name__ == "__main__":
    import time
    adc = MCP3008()
    print(f"MCP3008 dibuka di SPI bus={adc.bus} device={adc.device}, VREF={adc.vref}V")
    print("Reading all 8 channel every 1 seconds (Ctrl+C for stop)...\n")
    try:
        while True:
            readings = [f"CH{c}={adc.read_voltage(c):.3f}V" for c in range(8)]
            print(" | ".join(readings))
            time.sleep(1)
    except KeyboardInterrupt:
        adc.close()
