"""
YF-S201 Flow Sensor - Quick Test Script
Just for checking wiring/readings, standalone (no DB, no main.py integration).

Wiring:
- Red wire   -> 5V (VCC)
- Black wire -> GND
- Yellow wire (signal) -> through a logic level converter / voltage divider
                            (5V -> 3.3V) -> GPIO pin (BCM numbering)

YF-S201 spec: ~450 pulses per liter (varies slightly per unit/datasheet,
some say 450, some 480 — adjust PULSES_PER_LITER below if your readings
seem off compared to actual poured volume).
"""

import RPi.GPIO as GPIO
import time

# ─── Config ────────────────────────────────────────────────
FLOW_SENSOR_PIN = 17          # change to whichever GPIO pin you wired signal into
PULSES_PER_LITER = 450        # datasheet value, adjust if needed

# ─── State ─────────────────────────────────────────────────
pulse_count = 0


def _pulse_callback(channel):
    global pulse_count
    pulse_count += 1


# ─── Setup ─────────────────────────────────────────────────
GPIO.setmode(GPIO.BCM)
GPIO.setup(FLOW_SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.add_event_detect(FLOW_SENSOR_PIN, GPIO.FALLING, callback=_pulse_callback)

print(f"Listening for pulses on GPIO {FLOW_SENSOR_PIN}... Ctrl+C to stop.\n")

try:
    total_pulses = 0
    while True:
        time.sleep(1)  # measure over a 1-second window

        pulses_this_second = pulse_count
        pulse_count = 0  # reset counter for next window
        total_pulses += pulses_this_second

        flow_rate_lps = pulses_this_second / PULSES_PER_LITER          # liters per second
        flow_rate_lpm = flow_rate_lps * 60                              # liters per minute
        total_liters = total_pulses / PULSES_PER_LITER

        print(
            f"Pulses/sec: {pulses_this_second:3d} | "
            f"Flow: {flow_rate_lpm:6.2f} L/min | "
            f"Total: {total_liters:6.3f} L"
        )

except KeyboardInterrupt:
    print("\nStopped by user.")

finally:
    GPIO.cleanup()