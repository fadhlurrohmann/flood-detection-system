"""
TEST 1 — MCP3008 (ADC SPI)
Run BEFORE testing sensor analog apapun (MQ-2/MQ-135/soil), because
all sensor itu bergantung ke chip ini.

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
print("Make sure SPI sudah enabled: sudo raspi-config -> Interface -> SPI -> Yes")
print("Lalu check device: ls /dev/spidev* (harus muncul /dev/spidev0.0)\n")

try:
    adc = MCP3008()
    print(f"[OK] MCP3008 terbuka di SPI bus={adc.bus}, device={adc.device}, VREF={adc.vref}V\n")
except Exception as e:
    print(f"[FAIL] Tidak bisa buka MCP3008: {e}")
    print("\nKemungkinan penyebab:")
    print("  - SPI belum diaktifkan (raspi-config)")
    print("  - spidev belum terinstall (pip install spidev)")
    print("  - Wiring CLK/DOUT/DIN/CS wrong (check docs/Pinout.md)")
    sys.exit(1)

print("Reading all 8 channel selama 10 seconds (Ctrl+C for stop lebih awal)...")
print("Channel that TIDAK connected sensor akan menunjukkan value random/noise - itu NORMAL.\n")

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

print("\n[COMPLETE] If channel that ada sensornya (CH0-CH3) menunjukkan value")
print("that BERUBAH when Anda tutup sensor with tangan / kabel disentuh,")
print("berarti wiring SPI MCP3008 sudah correct.")
