"""
TEST 1 — MCP3008 (SPI ADC)
Run BEFORE testing any analog sensor (pressure/battery), because
all of those sensors depend on this chip.

Usage: python3 tests/test_mcp3008.py
"""
import sys
import time
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.mcp3008 import MCP3008

print("=" * 60)
print("  TEST MCP3008 (SPI ADC)")
print("=" * 60)
print("Make sure SPI is enabled: sudo raspi-config -> Interface -> SPI -> Yes")
print("Then check the device: ls /dev/spidev* (/dev/spidev0.0 must appear)\n")

try:
    adc = MCP3008()
    print(f"[OK] MCP3008 opened on SPI bus={adc.bus}, device={adc.device}, VREF={adc.vref}V\n")
except Exception as e:
    print(f"[FAIL] Cannot open the MCP3008: {e}")
    print("\nPossible causes:")
    print("  - SPI is not enabled (raspi-config)")
    print("  - spidev is not installed (pip install spidev)")
    print("  - Wrong CLK/DOUT/DIN/CS wiring (see docs/Pinout.md)")
    sys.exit(1)

print("Reading all 8 channels for 10 seconds (Ctrl+C to stop early)...")
print("Channels with NO sensor connected will show random values/noise - that is NORMAL.\n")

try:
    for i in range(10):
        readings = []
        for ch in range(8):
            raw = adc.read_raw(ch)
            volt = adc.read_voltage(ch)
            readings.append(f"CH{ch}={raw:4d}({volt:.2f}V)")
        print(" | ".join(readings))
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    adc.close()

print("\n[DONE] If the channels that have a sensor (CH0-CH3) show values")
print("that CHANGE when you cover the sensor with your hand / touch the wire,")
print("then the MCP3008 SPI wiring is correct.")
