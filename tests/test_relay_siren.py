"""
TEST 7 — Relay 5V + Sirine 12V/24V/220V 120dB (with LED flasher)

⚠️  WARNING: Sirine ini 120dB - SANGAT KERAS. Make sure Anda ready
    before menjalankan test ini (tutup telinga / jaga distance / beri tahu
    orang sekitar). Test ini akan correct-correct menyalakan sirine physical.

Usage: python3 tests/test_relay_siren.py
"""
import sys
import time
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alarm.siren import AlarmController

print("=" * 60)
print("  TEST Relay + Sirine 12V (120dB)")
print("=" * 60)
print("⚠️  Sirine akan BERBUNYI KERAS pada test ini.")
confirm = input("Ketik 'ya' for lanjut, or Enter for batal: ").strip().lower()
if confirm != "ya":
    print("Dibatalkan.")
    sys.exit(0)

try:
    ctrl = AlarmController()
    print("\n[OK] Relay diinisialisasi.\n")
except Exception as e:
    print(f"[FAIL] Gagal inisialisasi relay: {e}")
    sys.exit(1)

try:
    print("Tahap 1: Relay ON directly 2 seconds (check bunyi 'klik' relay + sirine active)...")
    ctrl.relay.on()
    time.sleep(2)
    ctrl.relay.off()
    print("Tahap 1 complete - relay OFF.\n")
    time.sleep(1)

    print("Tahap 2: Level WARNING selama 5 seconds (sirine berdenyut pelan 0.4s ON/1.6s OFF)...")
    ctrl.set_level(AlarmController.LEVEL_WARNING)
    time.sleep(5)

    print("Tahap 3: Level CRITICAL selama 3 seconds (sirine active TERUS)...")
    ctrl.set_level(AlarmController.LEVEL_CRITICAL)
    time.sleep(3)

finally:
    ctrl.silence()
    print("\n[SELESAI] Alarm dimatikan (relay OFF).")
    print("If sirine not bunyi sama sekali, check:")
    print("  - Wiring relay COM/NO ke jalur 12V sirine (see docs/Pinout.md)")
    print("  - active_low wrong (coba Relay(active_low=False) di alarm/relay.py)")
    print("  - Sumber 12V for sirine belum connected/aktif")
