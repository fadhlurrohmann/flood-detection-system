"""
TEST 1 — MCP3008 (ADC SPI)
Run BEFORE testing sensor analog anything (MQ-2/MQ-135/soil), because
all sensor that bergantung to chip this.

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
print("Make sure SPI already enabled: sudo raspi-config -> Interface -> SPI -> Yes")
print("Then check device: ls /dev/spidev* (must appears /dev/spidev0.0)\n")

try:
    adc = MCP3008()
    print(f"[OK] MCP3008 open in SPI bus={adc.bus}, device={adc.device}, VREF={adc.vref}V\n")
except Exception as e:
    print(f"[FAIL] Not can open MCP3008: {e}")
    print("\nKemungkinan penyebab:")
    print("  - SPI not yet enabled (raspi-config)")
    print("  - spidev not yet terinstall (pip install spidev)")
    print("  - Wiring CLK/DOUT/DIN/CS wrong (check docs/Pinout.md)")
    sys.exit(1)

print("Reading all 8 channel during 10 seconds (Ctrl+C for stop more early)...")
print("Channel that NOT connected sensor will shows value random/noise - that NORMAL.\n")

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

print("\n[COMPLETE] If channel that exists a sensor (CH0-CH3) shows value")
print("that CHANGES when You tutup sensor with hand / cable touched,")
print("means wiring SPI MCP3008 already correct.")
