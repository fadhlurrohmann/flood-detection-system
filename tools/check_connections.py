"""
EFWS — Connection check (config, DB, API endpoints, SIM modem) in one go.

Default mode is READ-ONLY toward the outside: it resolves DNS and does a GET
to EFWS_API_URL, but does not POST anything. Use the flags to go further.

Usage:
  python3 tools/check_connections.py                 # config + DB + API reachability + SIM
  python3 tools/check_connections.py --send          # also POST one test payload to all 4 endpoints
  python3 tools/check_connections.py --load 50       # also POST 50 telemetry payloads, report latency
  python3 tools/check_connections.py --load 50 --concurrency 5

Notes:
  - --send / --load hit the real backend in EFWS_API_URL. Point it at
    tools/mock_api_server.py or webhook.site if you don't want test data there.
  - Nothing is ever written to the real DB file. The DB write test uses a temp file.
  - The SIM check only runs with EFWS_RUN_MODE=hardware, and needs efws.service
    stopped (it opens /dev/ttyUSB* exclusively).
"""
import argparse
import json
import os
import socket
import sqlite3
import statistics
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

results = {"ok": 0, "warn": 0, "fail": 0}


def ok(msg):   results["ok"] += 1;   print(f"  [OK]   {msg}")
def warn(msg): results["warn"] += 1; print(f"  [WARN] {msg}")
def fail(msg): results["fail"] += 1; print(f"  [FAIL] {msg}")
def info(msg): print(f"         {msg}")
def section(title): print(f"\n== {title} ==")


# ─── 1. Config ───────────────────────────────────────────────────────────────
def check_config():
    section("1. Config (.env)")
    try:
        from config import settings
    except EnvironmentError as e:
        fail(f"Settings failed to load: {str(e).strip()}")
        return None

    info(f"RUN_MODE  : {settings.RUN_MODE}")
    info(f"DEVICE_ID : {settings.DEVICE_ID}")
    info(f"API_URL   : {settings.API_BASE_URL}")
    info(f"DB_PATH   : {settings.DB_PATH}")

    if "webhook.site/xxxxxxxx" in settings.API_BASE_URL:
        fail("EFWS_API_URL is still the placeholder from .env.example")
    else:
        ok("EFWS_API_URL is set")

    if settings.DEVICE_TOKEN in ("", "test"):
        warn("EFWS_DEVICE_TOKEN is empty/'test' -- a real backend will likely reject it (4xx)")
    return settings


# ─── 2. Database ─────────────────────────────────────────────────────────────
def check_db(settings):
    section("2. Database (SQLite)")

    # 2a. Real DB file -- opened read-only, never created or modified.
    path = settings.DB_PATH
    if not os.path.exists(path):
        warn(f"DB file does not exist yet: {path} (main.py creates it on first run)")
    else:
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity == "ok":
                ok(f"Opened read-only, integrity_check = ok ({os.path.getsize(path) / 1024:.0f} KB)")
            else:
                fail(f"integrity_check reported: {integrity}")

            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            missing = {"sensor_readings", "api_queue"} - tables
            if missing:
                fail(f"Missing tables: {', '.join(sorted(missing))}")
            else:
                n_read = conn.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0]
                last = conn.execute("SELECT MAX(timestamp) FROM sensor_readings").fetchone()[0]
                pending = conn.execute(
                    "SELECT COUNT(*) FROM api_queue WHERE sent=0 AND attempts<10").fetchone()[0]
                stale = conn.execute(
                    "SELECT COUNT(*) FROM api_queue WHERE sent=0 AND attempts>=10").fetchone()[0]
                ok(f"sensor_readings: {n_read} rows, last at {last or '-'}")
                (ok if pending == 0 else warn)(f"api_queue: {pending} pending (not yet delivered)")
                if stale:
                    warn(f"api_queue: {stale} items gave up after 10 attempts")
            conn.close()
        except sqlite3.Error as e:
            fail(f"Could not read DB: {e}")

    # 2b. Write/read round-trip on a temp DB, using the app's own DBManager.
    from database.db_manager import DBManager
    tmp = os.path.join(tempfile.gettempdir(), "efws_check_connections.db")
    if os.path.exists(tmp):
        os.remove(tmp)
    try:
        db = DBManager(db_path=tmp)
        payload = {"probe": "check_connections", "n": 1}
        db.queue_api("http://example/probe", payload)
        item = db.get_pending_queue()[0]
        db.mark_queue_sent(item["id"])
        if json.loads(item["payload"]) == payload and db.count_pending_queue() == 0:
            ok("DBManager write/read/mark-sent round-trip works (temp DB)")
        else:
            fail("DBManager round-trip returned unexpected data")
        db.close()
    except Exception as e:
        fail(f"DBManager round-trip error: {type(e).__name__}: {e}")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# ─── 3. API ──────────────────────────────────────────────────────────────────
def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _test_payloads(settings):
    base = {"deviceId": settings.DEVICE_ID, "deviceToken": settings.DEVICE_TOKEN}
    return {
        "location":  (settings.location_endpoint(),
                      {**base, "latitude": settings.DEVICE_LOCATION["lat"],
                       "longitude": settings.DEVICE_LOCATION["lon"]}),
        "telemetry": (settings.telemetry_endpoint(),
                      {**base, "telemetry": [{
                          "timestamp": _now_iso(), "waterLevel": 0.0, "distanceM": None,
                          "soilMoisture": {"surface": None, "deep": None}, "rainfallMm": 0.0}]}),
        "heartbeat": (settings.heartbeat_endpoint(), {**base, "batteryLevel": None}),
        "ack":       (settings.command_ack_endpoint(),
                      {**base, "commandId": "connection-check", "status": "SUCCESS", "error": ""}),
    }


def check_api(settings, do_send):
    section("3. API endpoint")
    url = urlparse(settings.API_BASE_URL)
    host = url.hostname
    port = url.port or (443 if url.scheme == "https" else 80)

    try:
        ip = socket.gethostbyname(host)
        ok(f"DNS: {host} -> {ip}")
    except socket.gaierror as e:
        fail(f"DNS lookup failed for {host}: {e}")
        return None

    try:
        t0 = time.time()
        socket.create_connection((host, port), timeout=5).close()
        ok(f"TCP connect to {host}:{port} in {(time.time() - t0) * 1000:.0f} ms")
    except OSError as e:
        fail(f"TCP connect to {host}:{port} failed: {e}")
        return None

    from communication.api_publisher import APIPublisher
    api = APIPublisher()
    try:
        t0 = time.time()
        r = api.session.get(settings.API_BASE_URL, timeout=10, verify=settings.API_VERIFY_SSL)
        ok(f"GET {settings.API_BASE_URL} -> HTTP {r.status_code} in {(time.time() - t0) * 1000:.0f} ms")
    except Exception as e:
        fail(f"GET failed (TLS/HTTP): {type(e).__name__}: {e}")
        return api

    if not do_send:
        info("Skipping POSTs (use --send to test all 4 endpoints)")
        return api

    # _post_once = single attempt, no retry sleep, no queueing.
    for name, (endpoint, payload) in _test_payloads(settings).items():
        t0 = time.time()
        delivered, status, resp_json, transient = api._post_once(endpoint, json.dumps(payload))
        ms = (time.time() - t0) * 1000
        if delivered:
            ok(f"POST {name:<9} -> HTTP {status} in {ms:.0f} ms")
            if name == "telemetry" and isinstance(resp_json, dict) and "config" in resp_json:
                info(f"backend sent config: {resp_json['config']}")
            if name == "heartbeat" and isinstance(resp_json, dict) and resp_json.get("commands"):
                info(f"backend sent commands: {resp_json['commands']}")
        elif status and not transient:
            warn(f"POST {name:<9} -> HTTP {status} (reachable, but backend rejected it -- token/payload?)")
        elif status:
            fail(f"POST {name:<9} -> HTTP {status} (server error)")
        else:
            fail(f"POST {name:<9} -> no response (network error/timeout)")
    return api


def load_test(settings, api, n, concurrency):
    section(f"4. Load test ({n} telemetry POSTs, concurrency {concurrency})")
    endpoint, payload = _test_payloads(settings)["telemetry"]
    body = json.dumps(payload)

    def one(_):
        t0 = time.time()
        delivered, status, _, _ = api._post_once(endpoint, body)
        return delivered, status, (time.time() - t0) * 1000

    t_start = time.time()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        runs = list(pool.map(one, range(n)))
    total = time.time() - t_start

    lat = sorted(r[2] for r in runs)
    good = sum(1 for r in runs if r[0])
    codes = {}
    for _, status, _ in runs:
        codes[status or "no-response"] = codes.get(status or "no-response", 0) + 1

    info(f"status codes: {codes}")
    info(f"latency ms  : min {lat[0]:.0f} / median {statistics.median(lat):.0f} / "
         f"p95 {lat[int(len(lat) * 0.95) - 1]:.0f} / max {lat[-1]:.0f}")
    info(f"throughput  : {n / total:.1f} req/s over {total:.1f} s")
    (ok if good == n else fail)(f"{good}/{n} delivered")


# ─── 5. SIM modem ────────────────────────────────────────────────────────────
CREG_STAT = {"0": "not registered, not searching", "1": "registered (home)",
             "2": "searching...", "3": "registration DENIED", "4": "unknown",
             "5": "registered (roaming)"}


def check_sim(settings):
    section("5. SIM modem")
    if settings.RUN_MODE != "hardware":
        info("Skipped: EFWS_RUN_MODE is not 'hardware'")
        return

    from communication.sim_detector import detect_sim
    try:
        sim = detect_sim(force_scan=True)
    except Exception as e:
        fail(f"detect_sim() failed: {type(e).__name__}: {e} (is efws.service still holding the port?)")
        return
    ok(f"Module {sim.module} on {sim.port}")

    try:
        cpin = sim._drv.send_at("AT+CPIN?")
        if "READY" in cpin:
            ok("SIM card detected, unlocked (CPIN READY)")
        elif "SIM PIN" in cpin:
            fail("SIM needs a PIN")
        else:
            fail(f"SIM card not ready: {cpin.strip() or 'no reply'} (inserted before power-on?)")

        csq = sim.signal_quality()
        try:
            rssi = int(csq.split("+CSQ:")[1].split(",")[0])
            if rssi == 99:
                fail("Signal: unknown/none (CSQ 99) -- check LTE antenna")
            else:
                (ok if rssi >= 10 else warn)(f"Signal: CSQ {rssi}/31 (~{-113 + 2 * rssi} dBm)")
        except (IndexError, ValueError):
            warn(f"Could not parse signal reply: {csq.strip()}")

        for cmd in ("AT+CREG?", "AT+CEREG?"):
            reply = sim._drv.send_at(cmd)
            try:
                stat = reply.split(":")[1].split(",")[1].strip()[0]
                label = CREG_STAT.get(stat, stat)
                (ok if stat in ("1", "5") else fail if stat == "3" else warn)(f"{cmd:<10} {label}")
            except IndexError:
                warn(f"{cmd:<10} unparsed reply: {reply.strip()}")
    finally:
        sim.close()


# ─── main ────────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description="EFWS connection check")
    p.add_argument("--send", action="store_true", help="POST one test payload to each of the 4 endpoints")
    p.add_argument("--load", type=int, metavar="N", help="POST N telemetry payloads and report latency")
    p.add_argument("--concurrency", type=int, default=1, help="parallel requests for --load (default 1)")
    p.add_argument("--skip-sim", action="store_true", help="skip the SIM modem check")
    args = p.parse_args()

    print("=" * 60)
    print("  EFWS — Connection check")
    print("=" * 60)

    settings = check_config()
    if settings is None:
        return 1

    check_db(settings)
    api = check_api(settings, args.send)
    if args.load and api is not None:
        load_test(settings, api, args.load, max(1, args.concurrency))
    if api is not None:
        api.close()
    if not args.skip_sim:
        check_sim(settings)

    print(f"\n== Summary: {results['ok']} OK, {results['warn']} WARN, {results['fail']} FAIL ==")
    return 1 if results["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
