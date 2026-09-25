"""
TEST — Integritas offline queue (queue) when signal lost.

Tujuan: memastikan payload that disimpan ke SQLite api_queue when API not
reachable (signal 4G hilang / EFWS_API_URL not reachable) TIDAK berubah
sedikit pun from payload original — baik when disimpan maupun when resent
(flush) after signal restored. Ini penting because data sensor pada when
kejadian (mis. level kritis) harus sampai ke server APA ADANYA, not
direkonstruksi/dihitung again from value sensor that sudah berubah.

Cara kerja test:
  1. Set EFWS_API_URL ke alamat that dijamin not reachable.
  2. Send satu payload contoh through APIPublisher.send_telemetry() (harus failed
     dan otomatis enter queue).
  3. Get kembali item queue from DB, bandingkan byte-demi-byte (deep equality)
     with payload original.
  4. Simulasikan signal restored (online=True paksa) lalu flush_queue() dan
     make sure payload that di-POST again (through monkeypatch _post_once) sama
     persis with payload original.

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
    print("  TEST — Integritas Offline Queue")
    print("=" * 60)

    tmp_db = os.path.join(tempfile.gettempdir(), "efws_queue_integrity_test.db")
    if os.path.exists(tmp_db):
        os.remove(tmp_db)

    db  = DBManager(db_path=tmp_db)
    api = APIPublisher()

    failures = []

    # 1) Simulasikan offline: send harus failed & otomatis enter queue
    ok = api.send_telemetry(SAMPLE_PAYLOAD, db=db)
    if ok:
        failures.append("send_telemetry() harusnya failed (endpoint sengaja unreachable)")
    else:
        print("  ✅ send_telemetry() failed seperti diharapkan (signal lost)")

    pending = db.get_pending_queue()
    if len(pending) != 1:
        failures.append(f"Jumlah item queue harus 1, dapat {len(pending)}")
    else:
        queued = json.loads(pending[0]["payload"])
        if queued == SAMPLE_PAYLOAD:
            print("  ✅ Payload di queue IDENTIK with payload original (deep equality)")
        else:
            failures.append(f"Payload di queue BERUBAH dari aslinya!\n  asli : {SAMPLE_PAYLOAD}\n  queue: {queued}")

    # 2) Simulasikan signal restored → flush_queue() harus resend payload
    #    that SAMA PERSIS (not payload new/dihitung again)
    sent_payloads = []
    original_post_once = api._post_once

    def fake_post_once(endpoint, body):
        sent_payloads.append(json.loads(body))
        # _post_once sekarang return 4-tuple: (delivered, status_code, response_json, transient)
        return True, 200, {"success": True}, False

    api._post_once = fake_post_once
    api.online = True  # paksa anggap signal sudah kembali
    api.flush_queue(db)
    api._post_once = original_post_once

    if len(sent_payloads) != 1:
        failures.append(f"flush_queue() harus mengirim 1 payload, terkirim {len(sent_payloads)}")
    elif sent_payloads[0] != SAMPLE_PAYLOAD:
        failures.append("Payload that di-flush ULANG not sama with payload original!")
    else:
        print("  ✅ Payload that di-flush again after signal restored IDENTIK with aslinya")

    remaining = db.count_pending_queue()
    if remaining != 0:
        failures.append(f"Queue harus kosong setelah flush sukses, sisa {remaining}")
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
        print("  ✅ All pengecekan integritas queue LULUS.")


if __name__ == "__main__":
    main()
