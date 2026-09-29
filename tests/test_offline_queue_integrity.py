"""
TEST - Offline queue integrity during signal loss.

This verifies that a payload stored in SQLite while the API is unreachable is
identical when later resent. A critical event must reach the server unchanged
rather than being reconstructed from newer sensor readings.

Method:
  1. Set EFWS_API_URL to a guaranteed unreachable address.
  2. Send a payload; it must fail and enter the queue automatically.
  3. Read it from the queue and compare it with the original payload.
  4. Simulate restored connectivity, flush the queue, and compare the resent body.

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
        "waterLevel": 2.1,
        "distanceM": 0.82,
        "soilMoisture": {"surface": 42.5, "deep": 48.0},
        "rainfallMm": 3.4,
    }]
}


def main():
    print("=" * 60)
    print("  TEST - Integrity Offline Queue")
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
        failures.append("send_telemetry() should fail because the endpoint is unreachable")
    else:
        print("  [OK] send_telemetry() failed like expected (signal lost)")

    pending = db.get_pending_queue()
    if len(pending) != 1:
        failures.append(f"Expected one queued item, got {len(pending)}")
    else:
        queued = json.loads(pending[0]["payload"])
        if queued == SAMPLE_PAYLOAD:
            print("  [OK] Queued payload is identical to the original")
        else:
            failures.append(f"Queued payload changed\n  original: {SAMPLE_PAYLOAD}\n  queued: {queued}")

    # 2) Simulate signal restored -> flush_queue() must resend payload
    #    that SAME EXACTLY (not payload new/calculated again)
    sent_payloads = []
    original_post_once = api._post_once

    def fake_post_once(endpoint, body):
        sent_payloads.append(json.loads(body))
        # _post_once now return 4-tuple: (delivered, status_code, response_json, transient)
        return True, 200, {"success": True}, False

    api._post_once = fake_post_once
    api.online = True
    api.flush_queue(db)
    api._post_once = original_post_once

    if len(sent_payloads) != 1:
        failures.append(f"flush_queue() should send one payload, sent {len(sent_payloads)}")
    elif sent_payloads[0] != SAMPLE_PAYLOAD:
        failures.append("The flushed payload differs from the original")
    else:
        print("  [OK] Flushed payload is identical to the original")

    remaining = db.count_pending_queue()
    if remaining != 0:
        failures.append(f"Queue should be empty after a successful flush; {remaining} remain")
    else:
        print("  [OK] Queue empty after successfully flushed")

    db.close()
    api.close()
    os.remove(tmp_db)

    print("\n" + "=" * 60)
    if failures:
        print("  [FAIL] FAILED")
        for f in failures:
            print(f"   - {f}")
        sys.exit(1)
    else:
        print("  [OK] All queue integrity checks passed.")


if __name__ == "__main__":
    main()
