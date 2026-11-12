"""
CHECK — A7670E / SIM7670E internet access (module-only, host-independent)

Verifies that the 4G module ITSELF can reach the internet, using the module's
own TCP/IP stack via AT commands. The host computer's network (WiFi, Ethernet,
the module's RNDIS adapter) is NOT involved, so a PASS here means the SIM,
antenna, operator registration, APN and data bearer all work.

Steps:
  1. Find the AT port (Windows COMx or Linux /dev/ttyUSBx) by probing with "AT".
  2. SIM ready (AT+CPIN?).
  3. Signal (AT+CSQ) and LTE/packet registration (AT+CEREG? / AT+CGREG?).
  4. Set APN, attach and activate the PDP context, read the assigned IP.
  5. HTTP GET through the module (AT+HTTPINIT / HTTPPARA / HTTPACTION) and
     check the status code from the "+HTTPACTION: 0,<status>,<len>" URC.

Like check_gps.py this lives in hardware_checks/ with a "check_" prefix so
pytest does not collect it. It only needs pyserial (no .env / config import),
so it can be run straight from a laptop with the module plugged in over USB.

Windows: install the SIMCom A76XX USB driver first; the AT port shows up in
Device Manager as something like "SimTech HS-USB AT Port 9011 (COM5)".

Usage:
  python tests/hardware_checks/check_internet.py
  python tests/hardware_checks/check_internet.py --port COM5
  python tests/hardware_checks/check_internet.py --port /dev/ttyUSB1 --apn internet
  python tests/hardware_checks/check_internet.py --url http://example.com/
"""
import re
import sys
import time
import argparse

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("pyserial is not installed - pip install pyserial")
    sys.exit(1)

OK, FAIL, WARN, INFO = "[OK]  ", "[FAIL]", "[WARN]", "[INFO]"
SEP = "-" * 64

DEFAULT_URL = "http://connectivitycheck.gstatic.com/generate_204"


def header(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")


def result(status, label, value=""):
    val = f"  -> {value}" if value else ""
    print(f"  {status} {label}{val}")


def send_at(ser, cmd, wait=1.0):
    """Send an AT command, return everything received within `wait` seconds."""
    ser.reset_input_buffer()
    ser.write((cmd + "\r\n").encode())
    time.sleep(wait)
    raw = ser.read(ser.in_waiting or 1)
    return raw.decode(errors="ignore").strip()


def wait_for(ser, pattern, timeout):
    """Read until `pattern` (regex) appears or `timeout` seconds pass. Returns the match or None."""
    buf = ""
    deadline = time.time() + timeout
    while time.time() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buf += chunk.decode(errors="ignore")
            m = re.search(pattern, buf)
            if m:
                return m
    return None


# ─── Step 1: port ────────────────────────────────────────────────
def find_port(preferred, baudrate):
    header("STEP 1: AT port detection")
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        result(FAIL, "No serial ports detected.")
        print("  Check the USB cable and (Windows) the SIMCom driver in Device Manager.")
        return None

    for p in ports:
        print(f"    {p.device:16s} | {p.description}")

    if preferred:
        candidates = [preferred]
    else:
        # Ports whose description says "AT" first (Windows driver names them), then the rest
        candidates = [p.device for p in sorted(ports, key=lambda p: "AT" not in p.description)]

    for dev in candidates:
        try:
            with serial.Serial(dev, baudrate, timeout=1) as ser:
                if "OK" in send_at(ser, "AT", wait=0.5):
                    result(OK, f"AT port: {dev}")
                    return dev
        except (serial.SerialException, OSError):
            continue

    result(FAIL, "No port answered 'AT' with 'OK'.", "use --port to force one")
    return None


# ─── Step 2: SIM ─────────────────────────────────────────────────
def check_sim(ser):
    header("STEP 2: SIM card")
    resp = send_at(ser, "AT+CPIN?")
    if "READY" in resp:
        result(OK, "SIM: READY")
        return True
    if "SIM PIN" in resp:
        result(FAIL, "SIM is PIN-locked.")
    else:
        result(FAIL, "SIM not detected.", repr(resp))
    return False


# ─── Step 3: signal + registration ───────────────────────────────
def check_network(ser, timeout=60):
    header("STEP 3: Signal & network registration")
    csq = re.search(r"\+CSQ: (\d+),", send_at(ser, "AT+CSQ"))
    rssi = int(csq.group(1)) if csq else 99
    if rssi == 99:
        result(WARN, "Signal unknown (99) - check the LTE antenna")
    else:
        result(OK if rssi >= 10 else WARN, f"Signal RSSI={rssi}/31 (~{-113 + 2 * rssi} dBm)")

    # The A7670E is LTE-only (Cat-1), so EPS registration (CEREG) is what matters;
    # CGREG is checked too in case the network reports it there.
    states = {"1": "home", "5": "roaming"}
    deadline = time.time() + timeout
    while True:
        for cmd, tag in (("AT+CEREG?", "CEREG"), ("AT+CGREG?", "CGREG")):
            m = re.search(rf"\+{tag}: \d+,(\d+)", send_at(ser, cmd))
            if m and m.group(1) in states:
                result(OK, f"Registered ({tag}, {states[m.group(1)]})")
                op = re.search(r'\+COPS: \d+,\d+,"([^"]+)"', send_at(ser, "AT+COPS?", wait=2))
                if op:
                    result(INFO, "Operator:", op.group(1))
                return True
        if time.time() >= deadline:
            break
        sys.stdout.write(f"\r  Waiting for registration... {int(deadline - time.time()):3d}s left")
        sys.stdout.flush()
        time.sleep(3)
    print()
    result(FAIL, f"Not registered on the network after {timeout}s.")
    return False


# ─── Step 4: data bearer ─────────────────────────────────────────
def check_bearer(ser, apn):
    header(f"STEP 4: Data bearer (APN '{apn}')")
    send_at(ser, f'AT+CGDCONT=1,"IP","{apn}"')

    if "+CGATT: 1" not in send_at(ser, "AT+CGATT?"):
        resp = send_at(ser, "AT+CGATT=1", wait=5)
        if "OK" not in resp:
            result(FAIL, "Packet attach failed (AT+CGATT=1).", repr(resp))
            return False
    result(OK, "Packet service attached")

    if "+CGACT: 1,1" not in send_at(ser, "AT+CGACT?"):
        resp = send_at(ser, "AT+CGACT=1,1", wait=5)
        if "OK" not in resp:
            result(FAIL, "PDP context activation failed - wrong APN?", repr(resp))
            return False

    ip = re.search(r"\+CGPADDR: 1,\"?(\d{1,3}(?:\.\d{1,3}){3})", send_at(ser, "AT+CGPADDR=1"))
    if not ip or ip.group(1) == "0.0.0.0":
        result(FAIL, "No IP assigned by the operator.")
        return False
    result(OK, "IP from operator:", ip.group(1))
    return True


# ─── Step 5: real HTTP request through the module ────────────────
def check_http(ser, url, timeout=60):
    header("STEP 5: HTTP GET through the module")
    result(INFO, "URL:", url)
    send_at(ser, "AT+HTTPTERM")  # clear a session left over from an earlier run

    try:
        if "OK" not in send_at(ser, "AT+HTTPINIT", wait=2):
            result(FAIL, "AT+HTTPINIT failed.")
            return False
        send_at(ser, f'AT+HTTPPARA="URL","{url}"')

        ser.reset_input_buffer()
        ser.write(b"AT+HTTPACTION=0\r\n")
        start = time.time()
        m = wait_for(ser, r"\+HTTPACTION: 0,(\d+),(\d+)", timeout)
        if not m:
            result(FAIL, f"No HTTP response within {timeout}s.")
            return False

        status, length = int(m.group(1)), int(m.group(2))
        elapsed = time.time() - start
        if 200 <= status < 400:
            result(OK, f"HTTP {status}, {length} bytes, {elapsed:.1f}s")
            return True
        # 7xx are module-side errors (e.g. 713 = DNS failure, 706 = timeout)
        result(FAIL, f"HTTP status {status}", "7xx = module network error (DNS/timeout/no bearer)")
        return False
    finally:
        send_at(ser, "AT+HTTPTERM")


def main():
    parser = argparse.ArgumentParser(description="A7670E/SIM7670E internet access check")
    parser.add_argument("--port", default=None, help="e.g. COM5 or /dev/ttyUSB1 (default: auto-detect)")
    parser.add_argument("--baudrate", default=115200, type=int)
    parser.add_argument("--apn", default="internet")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--reg-timeout", default=60, type=int, help="seconds to wait for network registration")
    args = parser.parse_args()

    print("\n" + "=" * 64)
    print("  A7670E / SIM7670E Internet Check (module-only)")
    print("=" * 64)

    port = find_port(args.port, args.baudrate)
    if not port:
        sys.exit(1)

    try:
        ser = serial.Serial(port, args.baudrate, timeout=1)
    except serial.SerialException as e:
        result(FAIL, f"Cannot open {port}: {e}")
        sys.exit(1)

    passed = False
    try:
        send_at(ser, "ATE0")  # no echo, keeps responses clean
        passed = (check_sim(ser)
                  and check_network(ser, args.reg_timeout)
                  and check_bearer(ser, args.apn)
                  and check_http(ser, args.url))
    finally:
        ser.close()

    header("RESULT: " + ("PASS - the module can reach the internet" if passed
                         else "FAIL - see the first [FAIL] above"))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
