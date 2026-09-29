"""
TEST 1 - MCP3008 (ADC SPI)
Run this before testing the pressure, soil, or battery sensors because they all
depend on this ADC.

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
print("Enable SPI first: sudo raspi-config -> Interface -> SPI -> Yes")
print("Then run ls /dev/spidev*; it must show /dev/spidev0.0.\n")

try:
    adc = MCP3008()
    print(f"[OK] MCP3008 open in SPI bus={adc.bus}, device={adc.device}, VREF={adc.vref}V\n")
except Exception as e:
    print(f"[FAIL] Could not open MCP3008: {e}")
    print("\nPossible causes:")
    print("  - SPI is not enabled (raspi-config)")
    print("  - spidev is not installed (pip install spidev)")
    print("  - Wiring CLK/DOUT/DIN/CS wrong (check docs/Pinout.md)")
    sys.exit(1)

print("Reading all eight channels for 10 seconds (Ctrl+C to stop)...")
print("Unconnected channels may show random noise; that is normal.\n")

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

print("\n[COMPLETE] A connected CH0-CH3 value should change when its sensor input changes.")
print("If it does, the MCP3008 SPI wiring is working.")
