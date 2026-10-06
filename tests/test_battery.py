"""
TEST — Modul Sensor Tegangan DC 0-25V (baterai, lewat MCP3008 CH3)

Cek dulu sebelum run:
  ls /dev/spidev*  → harus ada /dev/spidev0.0
  Pin S modul tersambung LANGSUNG ke MCP3008 CH3
  GND modul (sisi output, pin −) tersambung ke GND Pi / MCP3008 (ground bersama)

Tiap baris menampilkan 50 sampel cepat: raw min/median/max, tegangan di pin
MCP3008 (V_pin), dan tegangan baterai hasil hitungan. Di akhir ada diagnosis
otomatis kalau pembacaannya tidak stabil.

Usage: python3 tests/test_battery.py
"""
import sys, os, time, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from sensors.battery import BatterySensor

BURST = 50

print("=" * 60)
print(f"  TEST — Battery Voltage Sensor (MCP3008 CH{settings.ADC_CHANNEL_BATTERY})")
print("=" * 60)

sensor = BatterySensor()
print(f"VREF={sensor.vref}V  divider_ratio={sensor.ratio}  "
      f"(V_baterai = raw/1023 × {sensor.vref} × {sensor.ratio})")
print("Membaca 5x, tiap 2 detik (Ctrl+C untuk stop lebih awal)...\n")

all_samples = []
try:
    for i in range(5):
        samples = [sensor.adc.read_raw(sensor.channel) for _ in range(BURST)]
        all_samples += samples
        med   = statistics.median(samples)
        v_pin = med / 1023 * sensor.vref
        v_bat = sensor.raw_to_voltage(int(med))
        print(f"  [{i+1}] raw min/med/max = {min(samples):4d}/{int(med):4d}/{max(samples):4d}"
              f"  V_pin={v_pin:.3f}V  voltage={v_bat}V  percent={sensor.voltage_to_percent(v_bat)}%")
        time.sleep(2)
except KeyboardInterrupt:
    print("\nDihentikan oleh user.")

if not all_samples:
    sys.exit(0)

spread = max(all_samples) - min(all_samples)
v_pin  = statistics.median(all_samples) / 1023 * sensor.vref
print()
if spread > 30 or v_pin < 0.3:
    print(f"❌ Pembacaan TIDAK STABIL (selisih raw {spread}, V_pin median {v_pin:.2f}V).")
    print("   Input CH3 'mengambang' — MCP3008 tidak melihat tegangan yang jelas. Cek:")
    print("   1. GND modul (pin − sisi output) tersambung ke GND Pi / MCP3008 pin 14 (AGND)?")
    print("   2. Kabel S benar ke MCP3008 pin 4 (= CH3; pin 1 di sebelah tanda titik/lekukan)?")
    print("   3. Multimeter: MCP3008 pin 4 terhadap pin 14 harus ≈ V_baterai / 5 (mis. 2.65V).")
    print("   4. Tes ADC: jumper CH3 ke 3.3V → raw ≈ 1023; jumper CH3 ke GND → raw ≈ 0.")
    print("      Kalau ini juga acak → masalah di wiring MCP3008 (VDD/VREF/AGND/DGND/SPI).")
elif v_pin > 3.2:
    print(f"❌ V_pin {v_pin:.2f}V mentok di ~3.3V — CH3 ditarik ke 3.3V oleh sambungan lain.")
    print("   Pastikan pin 4 MCP3008 HANYA tersambung ke pin S modul (ukur pin 4 vs pin 14 ≈ 2.65V).")
else:
    print(f"✅ Stabil (selisih raw {spread}). Bandingkan voltage di atas dengan multimeter di")
    print("   terminal baterai; kalau beda, set EFWS_BATTERY_DIVIDER_RATIO = V_baterai / V_pin_S.")
