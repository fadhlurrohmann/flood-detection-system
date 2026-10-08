"""
MCP3008 driver (8-channel, 10-bit ADC, via SPI) — replaces the ADS1115.

The MCP3008 is used because the Pi 4 has no analog pins. All analog sensors
(pressure sensor, battery voltage sensor)
are connected to the same single MCP3008 chip, read over hardware SPI (SPI0, CE0).

IMPORTANT about voltage:
  - The MCP3008 VDD/VREF must be 3.3V (NOT 5V) because it is connected directly to
    the Pi with no level shifter on the SPI side.
  - The voltage on EVERY channel must be < 3.3V (VREF). Higher signals are
    brought down with a voltage divider (resistors), do NOT use a logic level
    converter: the 10k pull-up on the LLC module changes the analog voltage (the HV
    side is pulled to 5V, the LV side stalls at 3.3V) → wrong readings.

Default channel mapping (see docs/Pinout.md for wiring details):
  CH2 → Submersible pressure sensor, via burden resistor (direct, WITHOUT an LLC)
  CH3 → Battery voltage sensor module (direct, max ~2.9V)
  CH0, CH1, CH4-CH7 → spare/expansion

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
    """One instance represents one physical MCP3008 chip on SPI0/CE0."""

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
        """Read channel 0-7, return the raw value 0-1023 (10-bit)."""
        if not 0 <= channel <= 7:
            raise ValueError("MCP3008 channel must be 0-7")
        cmd = [1, (8 + channel) << 4, 0]
        resp = self.spi.xfer2(cmd)
        value = ((resp[1] & 3) << 8) + resp[2]
        return value

    def read_voltage(self, channel: int) -> float:
        raw = self.read_raw(channel)
        return round(raw / 1023.0 * self.vref, 4)

    def close(self):
        self.spi.close()


# ─── Singleton helper ──────────────────────────────────────────────
# All analog sensors share the SAME single physical MCP3008 chip, so
# all sensors should use the same SPI instance, rather than each
# opening its own SPI connection.
_instance = None


def get_mcp3008() -> "MCP3008":
    global _instance
    if _instance is None:
        _instance = MCP3008()
    return _instance


if __name__ == "__main__":
    import time
    adc = MCP3008()
    print(f"MCP3008 opened on SPI bus={adc.bus} device={adc.device}, VREF={adc.vref}V")
    print("Reading all 8 channels every 1 second (Ctrl+C to stop)...\n")
    try:
        while True:
            readings = [f"CH{c}={adc.read_voltage(c):.3f}V" for c in range(8)]
            print(" | ".join(readings))
            time.sleep(1)
    except KeyboardInterrupt:
        adc.close()
