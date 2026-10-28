#!/usr/bin/env python3
"""
Send AT commands to the A7670E and print the replies.

Usage:
  python3 scripts/at.py                          # default: read the USB dial-up settings
  python3 scripts/at.py AT+CSQ 'AT+CGACT?'       # any commands
  python3 scripts/at.py --port /dev/ttyUSB2 AT

Quote commands containing ? or $ so the shell leaves them alone.
"""
import sys
import time
import argparse

import serial

DEFAULT_CMDS = ["AT+DIALMODE?", "AT$MYCONFIG?", "AT+CGACT?", "AT+CGDCONT?"]

parser = argparse.ArgumentParser(description="Send AT commands to the A7670E")
parser.add_argument("--port", default="/dev/ttyUSB1")
parser.add_argument("--baudrate", default=115200, type=int)
parser.add_argument("cmds", nargs="*", default=DEFAULT_CMDS)
args = parser.parse_args()

try:
    ser = serial.Serial(args.port, args.baudrate, timeout=1)
except serial.SerialException as e:
    sys.exit(f"Cannot open {args.port}: {e}  (try --port /dev/ttyUSB2)")

with ser:
    for cmd in args.cmds:
        ser.reset_input_buffer()
        ser.write((cmd + "\r\n").encode())
        time.sleep(1)
        reply = ser.read(ser.in_waiting or 1).decode(errors="ignore").strip()
        print(f"{cmd:20s} -> {reply.replace(chr(13), '').replace(chr(10), ' | ')}")
