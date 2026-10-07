"""
TEST 7 — 5V Relay + 12V/24V/220V 120dB Siren (with LED flasher)

⚠️  WARNING: This siren is 120dB - VERY LOUD. Make sure you are ready
    before running this test (cover your ears / keep your distance / tell
    the people around you). This test will actually sound the physical siren.

Usage: python3 tests/test_relay_siren.py
"""
import sys
import time
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alarm.siren import AlarmController

print("=" * 60)
print("  TEST Relay + 12V Siren (120dB)")
print("=" * 60)
print("⚠️  The siren will sound LOUDLY in this test.")
confirm = input("Type 'yes' to continue, or press Enter to cancel: ").strip().lower()
if confirm != "yes":
    print("Cancelled.")
    sys.exit(0)

try:
    ctrl = AlarmController()
    print("\n[OK] Relay initialised.\n")
except Exception as e:
    print(f"[FAIL] Failed to initialise the relay: {e}")
    sys.exit(1)

try:
    print("Stage 1: Relay ON straight for 2 seconds (listen for the relay 'click' + the siren turning on)...")
    ctrl.relay.on()
    time.sleep(2)
    ctrl.relay.off()
    print("Stage 1 finished - relay OFF.\n")
    time.sleep(1)

    print("Stage 2: WARNING level for 5 seconds (siren pulses slowly 0.4s ON/1.6s OFF)...")
    ctrl.set_level(AlarmController.LEVEL_WARNING)
    time.sleep(5)

    print("Stage 3: CRITICAL level for 3 seconds (siren stays on CONTINUOUSLY)...")
    ctrl.set_level(AlarmController.LEVEL_CRITICAL)
    time.sleep(3)

finally:
    ctrl.silence()
    print("\n[DONE] Alarm turned off (relay OFF).")
    print("If the siren does not sound at all, check:")
    print("  - The relay COM/NO wiring to the siren's 12V line (see docs/Pinout.md)")
    print("  - Wrong active_low (try Relay(active_low=False) in alarm/relay.py)")
    print("  - The 12V source for the siren is not connected/active")
