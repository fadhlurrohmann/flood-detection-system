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

    print("Mengaktifkan GPS...")
    print(send_at(ser, "AT+CGNSSPWR=1", 2))

    print("Menunggu GPS fix...")
    time.sleep(10)

    for i in range(10):
        print(f"\nPercobaan GPS ke-{i+1}")
        gps = send_at(ser, "AT+CGNSSINFO", 3)
        print(gps)

        if "," in gps and "+CGNSSINFO:" in gps:
            print("GPS readable.")
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
#     print("Program dihentikan")


# from gpiozero import DigitalInputDevice
# from time import sleep

# MQ135_PIN = 17

# sensor = DigitalInputDevice(MQ135_PIN)

# print("Menunggu sensor pemanasan...")

# sleep(30)

# try:
#     while True:
#         if sensor.value == 0:
#             print("⚠️ Gas/asap detected!")
#         else:
#             print("Udara normal")

#         sleep(1)

# except KeyboardInterrupt:
#     print("Program dihentikan")


# """
# SIM7600E-H Diagnostic Test Script
# ===================================
# Run directly di Raspberry Pi for check all fungsi module:
#   1. Connection serial & AT command dasar
#   2. SIM card & registrasi jaringan
#   3. Kualitas signal
#   4. GPS fix (koordinat real)
#   5. Connection data (ping ke internet)

# Cara use:
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

# # ─── Warna terminal (ASCII safe, no emoji) ───────────────────────
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


# # ─── Test 1: Deteksi port serial ─────────────────────────────────
# def test_find_port(preferred: str = None) -> str | None:
#     header("TEST 1: Deteksi Port Serial")

#     ports = list(serial.tools.list_ports.comports())
#     if not ports:
#         result(FAIL, "None port serial detected.")
#         print("\n  Make sure SIM7600E HAT installed dan driver terinstall.")
#         print("  Coba: ls /dev/ttyUSB*")
#         return None

#     print(f"  Port that detected ({len(ports)}):")
#     for p in ports:
#         print(f"    {p.device:20s} | {p.description}")

#     # Prioritas port that used SIM7600E
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
#         result(OK, f"Akan use port: {chosen}")
#     else:
#         result(FAIL, "None port /dev/ttyUSB* ditemukan.")
#     return chosen


# # ─── Test 2: Connection serial & AT dasar ───────────────────────────
# def test_basic_at(ser: serial.Serial) -> bool:
#     header("TEST 2: Connection Serial & AT Command Dasar")

#     # AT - ping module
#     resp = send_at(ser, "AT")
#     if "OK" in resp:
#         result(OK, "AT command", "module merespons")
#     else:
#         result(FAIL, "AT command does not respond.", f"raw: {repr(resp)}")
#         print("\n  Possibly penyebab:")
#         print("  - Port wrong (coba --port /dev/ttyUSB1 or ttyUSB2)")
#         print("  - Baudrate wrong (default 115200)")
#         print("  - Module belum dinyalakan / power issue")
#         return False

#     # ATI - info module
#     resp = send_at(ser, "ATI")
#     result(INFO, "Info module:", resp.replace("\r\n", " | "))

#     # AT+CGSN - IMEI
#     resp = send_at(ser, "AT+CGSN")
#     imei = re.search(r"\d{15}", resp)
#     if imei:
#         result(OK, "IMEI:", imei.group())
#     else:
#         result(WARN, "IMEI not readable", f"raw: {repr(resp)}")

#     # AT+CGMR - versi firmware
#     resp = send_at(ser, "AT+CGMR")
#     result(INFO, "Firmware:", resp.replace("\r\n", " "))

#     return True


# # ─── Test 3: SIM card ────────────────────────────────────────────
# def test_sim_card(ser: serial.Serial) -> bool:
#     header("TEST 3: SIM Card")

#     # Check SIM installed
#     resp = send_at(ser, "AT+CIMI")
#     imsi = re.search(r"\d{10,15}", resp)
#     if imsi:
#         result(OK, "SIM installed. IMSI:", imsi.group())
#     else:
#         result(FAIL, "SIM not detected or belum unlock.")
#         print("  Make sure SIM card installed with correct.")
#         return False

#     # Check PIN
#     resp = send_at(ser, "AT+CPIN?")
#     if "READY" in resp:
#         result(OK, "SIM PIN status: READY (not needs PIN)")
#     elif "SIM PIN" in resp:
#         result(FAIL, "SIM masih terkunci PIN! Masukkan PIN dulu.")
#         return False
#     else:
#         result(WARN, "Status PIN:", resp)

#     # Operator
#     resp = send_at(ser, "AT+COPS?", wait=3)
#     op = re.search(r'\+COPS: \d+,\d+,"([^"]+)"', resp)
#     if op:
#         result(OK, "Operator:", op.group(1))
#     else:
#         result(WARN, "Operator belum readable (mungkin masih registrasi)", f"raw: {resp}")

#     return True


# # ─── Test 4: Kualitas signal ─────────────────────────────────────
# def test_signal(ser: serial.Serial) -> bool:
#     header("TEST 4: Kualitas Signal")

#     # Registrasi jaringan
#     resp = send_at(ser, "AT+CREG?")
#     creg = re.search(r"\+CREG: \d+,(\d+)", resp)
#     reg_status = {
#         "0": "Not terdaftar, not mencari",
#         "1": "Terdaftar (home network)",
#         "2": "Mencari jaringan...",
#         "3": "Registrasi rejected",
#         "5": "Terdaftar (roaming)",
#     }
#     if creg:
#         stat = creg.group(1)
#         desc = reg_status.get(stat, f"Status {stat}")
#         icon = OK if stat in ("1", "5") else WARN if stat == "2" else FAIL
#         result(icon, "Registrasi jaringan:", desc)
#         if stat not in ("1", "5"):
#             print("  Tunggu beberapa seconds dan coba lagi.")
#     else:
#         result(WARN, "Cannot read status registrasi")

#     # CSQ - signal strength
#     resp = send_at(ser, "AT+CSQ")
#     csq = re.search(r"\+CSQ: (\d+),(\d+)", resp)
#     if csq:
#         rssi = int(csq.group(1))
#         if rssi == 99:
#             result(WARN, "Signal: not diketahui (99) -- make sure antenna installed")
#         else:
#             dbm   = -113 + (rssi * 2)
#             level = "Lemah" if rssi < 10 else "Sedang" if rssi < 20 else "Kuat"
#             result(OK if rssi >= 10 else WARN,
#                    f"Signal: RSSI={rssi}/31, ~{dbm}dBm", level)
#     else:
#         result(FAIL, "Cannot read kualitas signal")
#         return False

#     # Tipe jaringan (4G/3G/2G)
#     resp = send_at(ser, "AT+CPSI?", wait=2)
#     if "+CPSI:" in resp:
#         parts = resp.split(":")[1].strip().split(",")
#         net_type = parts[0].strip() if parts else "?"
#         result(INFO, "Tipe jaringan:", net_type)

#     return True


# # ─── Test 5: GPS ─────────────────────────────────────────────────
# def test_gps(ser: serial.Serial, timeout: int = 90) -> bool:
#     header(f"TEST 5: GPS (timeout {timeout} seconds)")
#     print("  Make sure antenna GPS installed dan ada sky open.")
#     print("  Cold start bisa needs 30-90 seconds.\n")

#     # Turn on GPS engine
#     resp = send_at(ser, "AT+CGPS=1", wait=2)
#     if "OK" in resp or "already" in resp.lower():
#         result(OK, "GPS engine ON")
#     else:
#         result(FAIL, "GPS engine failed dinyalakan:", repr(resp))
#         return False

#     # Polling AT+CGPSINFO sampai fix or timeout
#     elapsed = 0
#     interval = 3
#     last_raw = ""

#     print(f"  Polling each {interval}s...")
#     while elapsed < timeout:
#         resp = send_at(ser, "AT+CGPSINFO", wait=1)
#         last_raw = resp

#         match = re.search(r"\+CGPSINFO:\s*([^\r\n]+)", resp)
#         if match:
#             parts = [p.strip() for p in match.group(1).split(",")]

#             if len(parts) >= 9 and parts[0] != "":
#                 # Ada fix - parse
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
#                     result(OK, "GPS FIX SUCCESSFUL!")
#                     print(f"\n  {'Latitude':<20}: {lat}")
#                     print(f"  {'Longitude':<20}: {lon}")
#                     print(f"  {'Altitude':<20}: {alt} m")
#                     print(f"  {'Kecepatan':<20}: {spd} km/h")
#                     print(f"  {'Tanggal (UTC)':<20}: {date_fmt}")
#                     print(f"  {'Waktu (UTC)':<20}: {utc_fmt}")
#                     print(f"\n  Google Maps: https://maps.google.com/?q={lat},{lon}")

#                     return True
#                 except Exception as e:
#                     result(WARN, f"Parse error: {e}")
#             else:
#                 sys.stdout.write(f"\r  [{elapsed:3d}s/{timeout}s] Menunggu fix... (belum ada signal GPS)")
#                 sys.stdout.flush()
#         else:
#             sys.stdout.write(f"\r  [{elapsed:3d}s/{timeout}s] None respons AT+CGPSINFO")
#             sys.stdout.flush()

#         time.sleep(interval)
#         elapsed += interval + 1

#     print()
#     result(FAIL, f"GPS timeout after {timeout} seconds.")
#     result(INFO, "Raw terakhir:", repr(last_raw[:100]))
#     print("\n  Tips:")
#     print("  - Pindah ke tempat lebih open (dekat jendela / outdoor)")
#     print("  - Tunggu lebih old: tambah --gps-timeout 180")
#     print("  - Check connection antenna GPS ke module")
#     return False


# # ─── Test 6: Connection data internet ───────────────────────────────
# def test_data_connection(ser: serial.Serial, apn: str = "internet") -> bool:
#     header("TEST 6: Connection Data Internet")

#     # Check apakah sudah dapat IP (via NetworkManager/ModemManager)
#     resp = send_at(ser, "AT+CGPADDR=1", wait=2)
#     ip = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', resp)
#     if ip:
#         result(OK, "IP address aktif:", ip.group(1))
#     else:
#         result(WARN, "Belum ada IP from modem directly")
#         result(INFO, "Check with: ip addr show  or  ping 8.8.8.8")

#     # Check APN that terkonfigurasi
#     resp = send_at(ser, "AT+CGDCONT?", wait=2)
#     result(INFO, "APN config:", resp.replace("\r\n", " | ").strip())

#     # Set APN if belum
#     if apn not in resp:
#         result(INFO, f"Setting APN ke '{apn}'...")
#         send_at(ser, f'AT+CGDCONT=1,"IP","{apn}"')
#         result(INFO, "APN diset. Restart modem if perlu.")

#     return True


# # ─── Main ─────────────────────────────────────────────────────────
# def main():
#     parser = argparse.ArgumentParser(description="SIM7600E Diagnostic Test")
#     parser.add_argument("--port",        default=None,    help="Port serial, contoh: /dev/ttyUSB2")
#     parser.add_argument("--baudrate",    default=115200,  type=int)
#     parser.add_argument("--gps-timeout", default=90,      type=int, help="Timeout GPS fix (seconds)")
#     parser.add_argument("--apn",         default="internet")
#     parser.add_argument("--skip-gps",   action="store_true", help="Skip test GPS")
#     args = parser.parse_args()

#     print("\n" + "=" * 60)
#     print("  SIM7600E-H Diagnostic Test")
#     print("=" * 60)

#     # Test 1: Temukan port
#     port = test_find_port(args.port)
#     if not port:
#         sys.exit(1)

#     # Buka connection serial
#     try:
#         ser = serial.Serial(port, args.baudrate, timeout=2)
#         result(OK, f"Serial open: {port} @ {args.baudrate} baud")
#     except Exception as e:
#         result(FAIL, f"Failed buka serial port: {e}")
#         print(f"\n  Coba: sudo chmod 666 {port}")
#         sys.exit(1)

#     passed = 0
#     total  = 0

#     try:
#         # Test 2: AT dasar
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
#             print(f"\n{INFO} Test GPS dilewati (--skip-gps)")

#         # Test 6: Data
#         total += 1
#         if test_data_connection(ser, apn=args.apn):
#             passed += 1

#     finally:
#         ser.close()

#     # ─── Ringkasan ───────────────────────────────────────────────
#     header(f"RINGKASAN: {passed}/{total} test lulus")
#     if passed == total:
#         print("  All test LULUS. Module ready digunakan.\n")
#     elif passed >= total - 1:
#         print("  Hampir all test lulus. Check warning di atas.\n")
#     else:
#         print("  Ada test that FAILED. Selesaikan masalah di atas.\n")
#         print("  Perintah debug tambahan:")
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