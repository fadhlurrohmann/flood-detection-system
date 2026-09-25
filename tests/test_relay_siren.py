"""
TEST 7 — Relay 5V + Siren 12V/24V/220V 120dB (with LED flasher)

⚠️  WARNING: Siren this 120dB - VERY LOUD. Make sure You ready
    before run test this (tutup telinga / jaga distance / beri tahu
    people nearby). Test this will correct-correct activating siren physical.

Usage: python3 tests/test_relay_siren.py
"""
import sys
import time
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alarm.siren import AlarmController

print("=" * 60)
print("  TEST Relay + Siren 12V (120dB)")
print("=" * 60)
print("⚠️  Siren will SOUND LOUD on test this.")
confirm = input("Ketik 'ya' for continue, or Enter for batal: ").strip().lower()
if confirm != "ya":
    print("Canceled.")
    sys.exit(0)

try:
    ctrl = AlarmController()
    print("\n[OK] Relay diinisialisasi.\n")
except Exception as e:
    print(f"[FAIL] Failed inisialisasi relay: {e}")
    sys.exit(1)

try:
    print("Stage 1: Relay ON directly 2 seconds (check sound 'click' relay + siren active)...")
    ctrl.relay.on()
    time.sleep(2)
    ctrl.relay.off()
    print("Stage 1 complete - relay OFF.\n")
    time.sleep(1)

    print("Stage 2: Level WARNING during 5 seconds (siren pulses slowly 0.4s ON/1.6s OFF)...")
    ctrl.set_level(AlarmController.LEVEL_WARNING)
    time.sleep(5)

    print("Stage 3: Level CRITICAL during 3 seconds (siren active CONTINUOUSLY)...")
    ctrl.set_level(AlarmController.LEVEL_CRITICAL)
    time.sleep(3)

finally:
    ctrl.silence()
    print("\n[COMPLETE] Alarm turned off (relay OFF).")
    print("If siren not sound at all, check:")
    print("  - Wiring relay COM/NO to route 12V siren (see docs/Pinout.md)")
    print("  - active_low wrong (try Relay(active_low=False) in alarm/relay.py)")
    print("  - Power source 12V for siren not yet connected/active")
