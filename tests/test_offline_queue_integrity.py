"""
TEST — Integrity offline queue (queue) when signal lost.

Purpose: ensuring payload that stored to SQLite api_queue when API not
reachable (signal 4G lost / EFWS_API_URL not reachable) NOT changes
even slightly at all from payload original — either when stored or when resent
(flush) after signal restored. This important because data sensor on when
kejadian (mis. level kritis) must until to server UNCHANGED, not
direkonstruksi/calculated again from value sensor that already changes.

Methods kerja test:
  1. Set EFWS_API_URL to address that guaranteed not reachable.
  2. Send one payload example through APIPublisher.send_telemetry() (must failed
     and automatically enter queue).
  3. Get again item queue from DB, compare byte-for-byte (deep equality)
     with payload original.
  4. Simulate signal restored (online=True force) then flush_queue() and
     make sure payload that in-POST again (through monkeypatch _post_once) same
     exactly with payload original.

Usage: python3 tests/test_offline_queue_integrity.py
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("EFWS_API_URL", "http://127.0.0.1:1/unreachable-for-test")

from database.db_manager import DBManager
from communication.api_publisher import APIPublisher

SAMPLE_PAYLOAD = {
    "deviceId":    "DEV-TEST-QUEUE",
    "deviceToken": "test",
    "telemetry": [{
        "timestamp":            "2026-07-07T00:00:00.000Z",
        "waterLevel":           2.1,
        "waterLevelCurrentMa":  12.4,
        "smokeLevel":           43.2,
        "temp":                 42.5,
        "humidity":             67.1,
        "soilMoisture":         12.7,
        "batteryLevel":         85.0,
        "flameDetected":        False,
        "windSpeed":            3.4,
    }]
}


def main():
    print("=" * 60)
    print("  TEST — Integrity Offline Queue")
    print("=" * 60)

    tmp_db = os.path.join(tempfile.gettempdir(), "efws_queue_integrity_test.db")
    if os.path.exists(tmp_db):
        os.remove(tmp_db)

    db  = DBManager(db_path=tmp_db)
    api = APIPublisher()

    failures = []

    # 1) Simulate offline: send must failed & automatically enter queue
    ok = api.send_telemetry(SAMPLE_PAYLOAD, db=db)
    if ok:
        failures.append("send_telemetry() should failed (endpoint intentionally unreachable)")
    else:
        print("  ✅ send_telemetry() failed like expected (signal lost)")

    pending = db.get_pending_queue()
    if len(pending) != 1:
        failures.append(f"Number item queue must 1, got {len(pending)}")
    else:
        queued = json.loads(pending[0]["payload"])
        if queued == SAMPLE_PAYLOAD:
            print("  ✅ Payload in queue IDENTICAL with payload original (deep equality)")
        else:
            failures.append(f"Payload in queue CHANGED from original!\n  original : {SAMPLE_PAYLOAD}\n  queue: {queued}")

    # 2) Simulate signal restored → flush_queue() must resend payload
    #    that SAME EXACTLY (not payload new/calculated again)
    sent_payloads = []
    original_post_once = api._post_once

    def fake_post_once(endpoint, body):
        sent_payloads.append(json.loads(body))
        # _post_once now return 4-tuple: (delivered, status_code, response_json, transient)
        return True, 200, {"success": True}, False

    api._post_once = fake_post_once
    api.online = True  # force assume signal already again
    api.flush_queue(db)
    api._post_once = original_post_once

    if len(sent_payloads) != 1:
        failures.append(f"flush_queue() must send 1 payload, sent {len(sent_payloads)}")
    elif sent_payloads[0] != SAMPLE_PAYLOAD:
        failures.append("Payload that in-flush AGAIN not same with payload original!")
    else:
        print("  ✅ Payload that in-flush again after signal restored IDENTICAL with original")

    remaining = db.count_pending_queue()
    if remaining != 0:
        failures.append(f"Queue must empty after flush sukses, remaining {remaining}")
    else:
        print("  ✅ Queue empty after successfully flushed")

    db.close()
    api.close()
    os.remove(tmp_db)

    print("\n" + "=" * 60)
    if failures:
        print("  ❌ FAILED")
        for f in failures:
            print(f"   - {f}")
        sys.exit(1)
    else:
        print("  ✅ All checks integrity queue PASSED.")


if __name__ == "__main__":
    main()
