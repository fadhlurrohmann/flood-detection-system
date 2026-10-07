import serial
import time

PORT = "/dev/ttyUSB2"
BAUDRATE = 115200

def send_at(ser, cmd, delay=1):
    ser.write((cmd + "\r").encode())
    time.sleep(delay)
    response = ser.read_all().decode(errors="ignore")
    return response.strip()

def main():
    ser = serial.Serial(PORT, BAUDRATE, timeout=3)

    print(send_at(ser, "AT"))
    print(send_at(ser, "ATI"))
    print(send_at(ser, "AT+CPIN?"))
    print(send_at(ser, "AT+CSQ"))

    print("Enabling GPS...")
    print(send_at(ser, "AT+CGNSSPWR=1", 2))

    print("Waiting for GPS fix...")
    time.sleep(10)

    for i in range(10):
        print(f"\nGPS attempt #{i+1}")
        gps = send_at(ser, "AT+CGNSSINFO", 3)
        print(gps)

        if "," in gps and "+CGNSSINFO:" in gps:
            print("GPS read.")
            break

        time.sleep(5)

    ser.close()

if __name__ == "__main__":
    main()

# from gpiozero import Buzzer
# from time import sleep

# BUZZER_PIN = 16

# buzzer = Buzzer(BUZZER_PIN)

# try:
#     while True:
#         print("Buzzer ON")
#         buzzer.on()
#         sleep(1)

#         print("Buzzer OFF")
#         buzzer.off()
#         sleep(1)

# except KeyboardInterrupt:
#     buzzer.off()
#     print("Program stopped")


# """
# SIM7600E-H Diagnostic Test Script
# ===================================
# Run directly on the Raspberry Pi to check all module functions:
#   1. Serial connection & basic AT commands
#   2. SIM card & network registration
#   3. Signal quality
#   4. GPS fix (real coordinates)
#   5. Data connection (ping the internet)

# Usage:
#   python test_sim7600.py
#   python test_sim7600.py --port /dev/ttyUSB2
#   python test_sim7600.py --port /dev/ttyUSB2 --gps-timeout 120
# """
# import sys
# import re
# import time
# import argparse
# import serial
# import serial.tools.list_ports

# # ─── Terminal markers (ASCII safe, no emoji) ─────────────────────
# OK   = "[OK]  "
# FAIL = "[FAIL]"
# WARN = "[WARN]"
# INFO = "[INFO]"
# SEP  = "-" * 60


# def header(title: str):
#     print(f"\n{SEP}")
#     print(f"  {title}")
#     print(SEP)


# def result(status: str, label: str, value: str = ""):
#     val = f"  -> {value}" if value else ""
#     print(f"  {status} {label}{val}")


# # ─── Serial helper ───────────────────────────────────────────────
# def send_at(ser: serial.Serial, cmd: str, wait: float = 1.5) -> str:
#     ser.reset_input_buffer()
#     ser.write((cmd + "\r\n").encode())
#     time.sleep(wait)
#     raw = ser.read(ser.in_waiting or 1)
#     return raw.decode(errors="ignore").strip()


# # ─── Test 1: Detect the serial port ──────────────────────────────
# def test_find_port(preferred: str = None) -> str | None:
#     header("TEST 1: Serial Port Detection")

#     ports = list(serial.tools.list_ports.comports())
#     if not ports:
#         result(FAIL, "No serial port detected.")
#         print("\n  Make sure the SIM7600E HAT is attached and the driver is installed.")
#         print("  Try: ls /dev/ttyUSB*")
#         return None

#     print(f"  Detected ports ({len(ports)}):")
#     for p in ports:
#         print(f"    {p.device:20s} | {p.description}")

#     # Priority of the ports used by the SIM7600E
#     candidates = [p.device for p in ports if "USB" in p.device]
#     sim_candidates = ["/dev/ttyUSB2", "/dev/ttyUSB1", "/dev/ttyUSB0"]

#     chosen = None
#     if preferred and preferred in [p.device for p in ports]:
#         chosen = preferred
#     else:
#         for c in sim_candidates:
#             if c in candidates:
#                 chosen = c
#                 break
#         if not chosen and candidates:
#             chosen = candidates[0]

#     if chosen:
#         result(OK, f"Will use port: {chosen}")
#     else:
#         result(FAIL, "No /dev/ttyUSB* port found.")
#     return chosen


# # ─── Test 2: Serial connection & basic AT ────────────────────────
# def test_basic_at(ser: serial.Serial) -> bool:
#     header("TEST 2: Serial Connection & Basic AT Commands")

#     # AT - ping the module
#     resp = send_at(ser, "AT")
#     if "OK" in resp:
#         result(OK, "AT command", "module responds")
#     else:
#         result(FAIL, "AT command does not respond.", f"raw: {repr(resp)}")
#         print("\n  Possible causes:")
#         print("  - Wrong port (try --port /dev/ttyUSB1 or ttyUSB2)")
#         print("  - Wrong baudrate (default 115200)")
#         print("  - Module not powered on / power issue")
#         return False

#     # ATI - module info
#     resp = send_at(ser, "ATI")
#     result(INFO, "Module info:", resp.replace("\r\n", " | "))

#     # AT+CGSN - IMEI
#     resp = send_at(ser, "AT+CGSN")
#     imei = re.search(r"\d{15}", resp)
#     if imei:
#         result(OK, "IMEI:", imei.group())
#     else:
#         result(WARN, "IMEI could not be read", f"raw: {repr(resp)}")

#     # AT+CGMR - firmware version
#     resp = send_at(ser, "AT+CGMR")
#     result(INFO, "Firmware:", resp.replace("\r\n", " "))

#     return True


# # ─── Test 3: SIM card ────────────────────────────────────────────
# def test_sim_card(ser: serial.Serial) -> bool:
#     header("TEST 3: SIM Card")

#     # Check the SIM is inserted
#     resp = send_at(ser, "AT+CIMI")
#     imsi = re.search(r"\d{10,15}", resp)
#     if imsi:
#         result(OK, "SIM inserted. IMSI:", imsi.group())
#     else:
#         result(FAIL, "SIM not detected or not unlocked yet.")
#         print("  Make sure the SIM card is inserted correctly.")
#         return False

#     # Check the PIN
#     resp = send_at(ser, "AT+CPIN?")
#     if "READY" in resp:
#         result(OK, "SIM PIN status: READY (no PIN needed)")
#     elif "SIM PIN" in resp:
#         result(FAIL, "SIM is still PIN-locked! Enter the PIN first.")
#         return False
#     else:
#         result(WARN, "PIN status:", resp)

#     # Operator
#     resp = send_at(ser, "AT+COPS?", wait=3)
#     op = re.search(r'\+COPS: \d+,\d+,"([^"]+)"', resp)
#     if op:
#         result(OK, "Operator:", op.group(1))
#     else:
#         result(WARN, "Operator not read yet (may still be registering)", f"raw: {resp}")

#     return True


# # ─── Test 4: Signal quality ──────────────────────────────────────
# def test_signal(ser: serial.Serial) -> bool:
#     header("TEST 4: Signal Quality")

#     # Network registration
#     resp = send_at(ser, "AT+CREG?")
#     creg = re.search(r"\+CREG: \d+,(\d+)", resp)
#     reg_status = {
#         "0": "Not registered, not searching",
#         "1": "Registered (home network)",
#         "2": "Searching for a network...",
#         "3": "Registration denied",
#         "5": "Registered (roaming)",
#     }
#     if creg:
#         stat = creg.group(1)
#         desc = reg_status.get(stat, f"Status {stat}")
#         icon = OK if stat in ("1", "5") else WARN if stat == "2" else FAIL
#         result(icon, "Network registration:", desc)
#         if stat not in ("1", "5"):
#             print("  Wait a few seconds and try again.")
#     else:
#         result(WARN, "Could not read the registration status")

#     # CSQ - signal strength
#     resp = send_at(ser, "AT+CSQ")
#     csq = re.search(r"\+CSQ: (\d+),(\d+)", resp)
#     if csq:
#         rssi = int(csq.group(1))
#         if rssi == 99:
#             result(WARN, "Signal: unknown (99) -- make sure the antenna is attached")
#         else:
#             dbm   = -113 + (rssi * 2)
#             level = "Weak" if rssi < 10 else "Medium" if rssi < 20 else "Strong"
#             result(OK if rssi >= 10 else WARN,
#                    f"Signal: RSSI={rssi}/31, ~{dbm}dBm", level)
#     else:
#         result(FAIL, "Could not read the signal quality")
#         return False

#     # Network type (4G/3G/2G)
#     resp = send_at(ser, "AT+CPSI?", wait=2)
#     if "+CPSI:" in resp:
#         parts = resp.split(":")[1].strip().split(",")
#         net_type = parts[0].strip() if parts else "?"
#         result(INFO, "Network type:", net_type)

#     return True


# # ─── Test 5: GPS ─────────────────────────────────────────────────
# def test_gps(ser: serial.Serial, timeout: int = 90) -> bool:
#     header(f"TEST 5: GPS (timeout {timeout} seconds)")
#     print("  Make sure the GPS antenna is attached and the sky is open.")
#     print("  A cold start can take 30-90 seconds.\n")

#     # Turn on the GPS engine
#     resp = send_at(ser, "AT+CGPS=1", wait=2)
#     if "OK" in resp or "already" in resp.lower():
#         result(OK, "GPS engine ON")
#     else:
#         result(FAIL, "GPS engine failed to turn on:", repr(resp))
#         return False

#     # Poll AT+CGPSINFO until a fix or a timeout
#     elapsed = 0
#     interval = 3
#     last_raw = ""

#     print(f"  Polling every {interval}s...")
#     while elapsed < timeout:
#         resp = send_at(ser, "AT+CGPSINFO", wait=1)
#         last_raw = resp

#         match = re.search(r"\+CGPSINFO:\s*([^\r\n]+)", resp)
#         if match:
#             parts = [p.strip() for p in match.group(1).split(",")]

#             if len(parts) >= 9 and parts[0] != "":
#                 # Fix acquired - parse
#                 try:
#                     def nmea_to_dd(nmea, direction):
#                         dot = nmea.index(".")
#                         deg = float(nmea[:dot - 2])
#                         minutes = float(nmea[dot - 2:])
#                         dd = deg + minutes / 60.0
#                         if direction in ("S", "W"):
#                             dd = -dd
#                         return round(dd, 6)

#                     lat  = nmea_to_dd(parts[0], parts[1])
#                     lon  = nmea_to_dd(parts[2], parts[3])
#                     alt  = float(parts[6]) if parts[6] else 0
#                     spd  = round(float(parts[7]) * 1.852, 2) if parts[7] else 0
#                     date = parts[4]
#                     utc  = parts[5]

#                     date_fmt = f"{date[:2]}/{date[2:4]}/20{date[4:]}" if len(date) == 6 else date
#                     utc_fmt  = f"{utc[:2]}:{utc[2:4]}:{utc[4:]}" if len(utc) >= 6 else utc

#                     print()
#                     result(OK, "GPS FIX SUCCEEDED!")
#                     print(f"\n  {'Latitude':<20}: {lat}")
#                     print(f"  {'Longitude':<20}: {lon}")
#                     print(f"  {'Altitude':<20}: {alt} m")
#                     print(f"  {'Speed':<20}: {spd} km/h")
#                     print(f"  {'Date (UTC)':<20}: {date_fmt}")
#                     print(f"  {'Time (UTC)':<20}: {utc_fmt}")
#                     print(f"\n  Google Maps: https://maps.google.com/?q={lat},{lon}")

#                     return True
#                 except Exception as e:
#                     result(WARN, f"Parse error: {e}")
#             else:
#                 sys.stdout.write(f"\r  [{elapsed:3d}s/{timeout}s] Waiting for a fix... (no GPS signal yet)")
#                 sys.stdout.flush()
#         else:
#             sys.stdout.write(f"\r  [{elapsed:3d}s/{timeout}s] No response to AT+CGPSINFO")
#             sys.stdout.flush()

#         time.sleep(interval)
#         elapsed += interval + 1

#     print()
#     result(FAIL, f"GPS timeout after {timeout} seconds.")
#     result(INFO, "Last raw:", repr(last_raw[:100]))
#     print("\n  Tips:")
#     print("  - Move somewhere more open (near a window / outdoors)")
#     print("  - Wait longer: add --gps-timeout 180")
#     print("  - Check the GPS antenna connection to the module")
#     return False


# # ─── Test 6: Internet data connection ────────────────────────────
# def test_data_connection(ser: serial.Serial, apn: str = "internet") -> bool:
#     header("TEST 6: Internet Data Connection")

#     # Check whether an IP has been obtained (via NetworkManager/ModemManager)
#     resp = send_at(ser, "AT+CGPADDR=1", wait=2)
#     ip = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', resp)
#     if ip:
#         result(OK, "IP address active:", ip.group(1))
#     else:
#         result(WARN, "No IP from the modem directly yet")
#         result(INFO, "Check with: ip addr show  or  ping 8.8.8.8")

#     # Check the configured APN
#     resp = send_at(ser, "AT+CGDCONT?", wait=2)
#     result(INFO, "APN config:", resp.replace("\r\n", " | ").strip())

#     # Set the APN if it is not set yet
#     if apn not in resp:
#         result(INFO, f"Setting APN to '{apn}'...")
#         send_at(ser, f'AT+CGDCONT=1,"IP","{apn}"')
#         result(INFO, "APN set. Restart the modem if needed.")

#     return True


# # ─── Main ─────────────────────────────────────────────────────────
# def main():
#     parser = argparse.ArgumentParser(description="SIM7600E Diagnostic Test")
#     parser.add_argument("--port",        default=None,    help="Serial port, e.g. /dev/ttyUSB2")
#     parser.add_argument("--baudrate",    default=115200,  type=int)
#     parser.add_argument("--gps-timeout", default=90,      type=int, help="GPS fix timeout (seconds)")
#     parser.add_argument("--apn",         default="internet")
#     parser.add_argument("--skip-gps",   action="store_true", help="Skip the GPS test")
#     args = parser.parse_args()

#     print("\n" + "=" * 60)
#     print("  SIM7600E-H Diagnostic Test")
#     print("=" * 60)

#     # Test 1: Find the port
#     port = test_find_port(args.port)
#     if not port:
#         sys.exit(1)

#     # Open the serial connection
#     try:
#         ser = serial.Serial(port, args.baudrate, timeout=2)
#         result(OK, f"Serial opened: {port} @ {args.baudrate} baud")
#     except Exception as e:
#         result(FAIL, f"Failed to open the serial port: {e}")
#         print(f"\n  Try: sudo chmod 666 {port}")
#         sys.exit(1)

#     passed = 0
#     total  = 0

#     try:
#         # Test 2: Basic AT
#         total += 1
#         if test_basic_at(ser):
#             passed += 1

#         # Test 3: SIM card
#         total += 1
#         if test_sim_card(ser):
#             passed += 1

#         # Test 4: Signal
#         total += 1
#         if test_signal(ser):
#             passed += 1

#         # Test 5: GPS
#         if not args.skip_gps:
#             total += 1
#             if test_gps(ser, timeout=args.gps_timeout):
#                 passed += 1
#         else:
#             print(f"\n{INFO} GPS test skipped (--skip-gps)")

#         # Test 6: Data
#         total += 1
#         if test_data_connection(ser, apn=args.apn):
#             passed += 1

#     finally:
#         ser.close()

#     # ─── Summary ─────────────────────────────────────────────────
#     header(f"SUMMARY: {passed}/{total} tests passed")
#     if passed == total:
#         print("  All tests PASSED. The module is ready to use.\n")
#     elif passed >= total - 1:
#         print("  Almost all tests passed. Check the warnings above.\n")
#     else:
#         print("  Some tests FAILED. Resolve the problems above.\n")
#         print("  Additional debug commands:")
#         print("    ls -la /dev/ttyUSB*")
#         print("    dmesg | grep ttyUSB")
#         print("    sudo systemctl status ModemManager")


# if __name__ == "__main__":
#     main()



# # Testing SIM7600E-H module with AT commands and GPS functionality. The script includes tests for serial connection, SIM card detection, signal quality, GPS fix, and data connection. It provides detailed output and suggestions for troubleshooting if any test fails.
# import serial
# import time

# ser = serial.Serial("/dev/ttyUSB2", 115200, timeout=2)

# ser.write(b'AT\r')
# time.sleep(1)
# print(ser.read_all().decode())

# ser.write(b'AT+CGPS=1\r')
# time.sleep(1)
# print(ser.read_all().decode())

# time.sleep(5)

# ser.write(b'AT+CGPSINFO\r')
# time.sleep(1)
# print(ser.read_all().decode())

# ser.close()
