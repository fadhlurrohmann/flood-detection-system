"""
TEST — Offline queue integrity when the signal is lost.

Goal: make sure the payload saved to the SQLite api_queue while the API is
unreachable (4G signal lost / EFWS_API_URL unreachable) does NOT change
in the slightest from the original payload — both when saved and when re-sent
(flushed) after the signal returns. This matters because the sensor data at the
time of the event (e.g. a critical level) must reach the server AS-IS, not
reconstructed/recomputed from sensor values that have since changed.

How the test works:
  1. Set EFWS_API_URL to an address guaranteed to be unreachable.
  2. Send one sample payload through APIPublisher.send_telemetry() (must fail
     and automatically go into the queue).
  3. Fetch the queue item back from the DB, compare byte-for-byte (deep equality)
     with the original payload.
  4. Simulate the signal returning (force online=True) then flush_queue() and
     make sure the payload that is re-POSTed (via a monkeypatched _post_once) is exactly
     the same as the original payload.

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
        "temp":                 42.5,
        "humidity":             67.1,
        "batteryLevel":         85.0,
        "flameDetected":        False,
        "windSpeed":            3.4,
    }]
}


def main():
    print("=" * 60)
    print("  TEST — Offline Queue Integrity")
    print("=" * 60)

    tmp_db = os.path.join(tempfile.gettempdir(), "efws_queue_integrity_test.db")
    if os.path.exists(tmp_db):
        os.remove(tmp_db)

    db  = DBManager(db_path=tmp_db)
    api = APIPublisher()

    failures = []

    # 1) Simulate offline: the send must fail & automatically go into the queue
    ok = api.send_telemetry(SAMPLE_PAYLOAD, db=db)
    if ok:
        failures.append("send_telemetry() should have failed (endpoint is deliberately unreachable)")
    else:
        print("  ✅ send_telemetry() failed as expected (signal lost)")

    pending = db.get_pending_queue()
    if len(pending) != 1:
        failures.append(f"The number of queue items must be 1, got {len(pending)}")
    else:
        queued = json.loads(pending[0]["payload"])
        if queued == SAMPLE_PAYLOAD:
            print("  ✅ The payload in the queue is IDENTICAL to the original payload (deep equality)")
        else:
            failures.append(f"The payload in the queue CHANGED from the original!\n  original: {SAMPLE_PAYLOAD}\n  queue   : {queued}")

    # 2) Simulate the signal returning → flush_queue() must re-send the EXACT
    #    SAME payload (not a new/recomputed one)
    sent_payloads = []
    original_post_once = api._post_once

    def fake_post_once(endpoint, body):
        sent_payloads.append(json.loads(body))
        # _post_once now returns a 4-tuple: (delivered, status_code, response_json, transient)
        return True, 200, {"success": True}, False

    api._post_once = fake_post_once
    api.online = True  # force the signal to be considered back
    api.flush_queue(db)
    api._post_once = original_post_once

    if len(sent_payloads) != 1:
        failures.append(f"flush_queue() must send 1 payload, {len(sent_payloads)} were sent")
    elif sent_payloads[0] != SAMPLE_PAYLOAD:
        failures.append("The payload that was RE-flushed is not the same as the original payload!")
    else:
        print("  ✅ The payload re-flushed after the signal returned is IDENTICAL to the original")

    remaining = db.count_pending_queue()
    if remaining != 0:
        failures.append(f"The queue must be empty after a successful flush, {remaining} remain")
    else:
        print("  ✅ The queue is empty after being flushed successfully")

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
        print("  ✅ All queue integrity checks PASSED.")


if __name__ == "__main__":
    main()
