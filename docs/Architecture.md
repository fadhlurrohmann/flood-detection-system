# EFWS Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     POWER SYSTEM                                         │
│  [Solar Panel 100W] → [SCC 20A PWM] → [LiFePO4 12V]                      │
│       [LiFePO4 12V] → [Buck Converter 12V→5V] → [Raspberry Pi 4 USB-C]   │
└──────────────────────────────────────────────────────────────────────────┘
                                       5V/12V/loop
                                        │
┌──────────────┐   I2C   ┌─────────────▼───────────── ┐   GPIO O  ┌────────────┐
│ BME280 (0x76)│◄───────►│                            │──────────►│ Relay 5V   │──►12V Siren
│Rainfall SEN0575        |                            |           |            |
|  GY-MS5837   │         │      Raspberry Pi 4        │           └────────────┘
├──────────────┤  SPI    │      (main.py orchestrator)│
│LLC > MCP3008 │◄───────►│                            │   GPIO I  ┌────────────┐
│CH0: Pressure │         │                            │◄──────────│ JSN-SR04T  │
│CH1: Battery  │         │                            │           │ YF-S201    │
│              │         │                            │           │  (digital) |
│              |         |                            |           |Wind Dir    |
│              │         │                            │           └────────────┘
└──────────────┘         │                            │
┌──────────────┐  USB    │                            │  USB/UART  ┌─────────────┐
│ RS485 (s/d   │◄───────►│                            │───────────►│ A7670E /    │──► 4G 9Network
│ Anemometer   │         │                            │            │ SIM7600     │
└──────────────┘         └────────────-─┬─────────────┘            │ (satu saja) │
                                        │                          └─────────────┘
                          ┌─────────────┴──────────────┐
                          │ 1) store to SQLite DULU    │
                          │ 2) local evaluation(siren) │
                          │ 3) try ending to REST API  │
                          │ 4) fail → offline queue    │
                          └─────────────┬──────────────┘
                                        ▼
                    EWS_API_URL/sensors/telemetry (backend)
                    ── backend will store alarm level &
                        threshold valuation "resmi"
```

## Thread Model (6 Thread)
`main.py` runs **6 independent threads** concurrently from startup.
Failure in one thread never stops the other threads.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  MAIN THREAD (sensor sampling loop)         every SENSOR_READ_INTERVAL_SEC  │
│  ─ read all sensor (.read() each driver)                                    │
│  ─ count water level (JSN + Submersible weighted formula)                   │
│  ─ Evaluasi threshold active (remote-first per-field, localfallback )       │
│  ─ Set/clear _emergency Event (single source of truth)                      │
│  ─ local siren: AlarmController.set_level("critical"/"normal")              │
│  ─ Update _latest_data snapshot (Publisher read other thread )              │
│   DOES NOT: send to API, store to SQLite, get GPS                           │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │ _latest_data snapshot (lock)
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌────────────────┐ ┌─────────────────┐ ┌────────────────────────────────────┐
│ LOCATION       │ │ TELEMETRY       │ │ HEARTBEAT                          │
│ PUBLISHER      │ │ PUBLISHER       │ │ PUBLISHER                          │
│                │ │                 │ │                                    │
│ Interval:      │ │ Interval ADAPTIF│ │ Interval:                          │
│ 1800s (tetap)  │ │ Normal: 1800s   │ │ 300s (tetap)                       │
│                │ │ Emergency: 600s │ │                                    │
│ 1. get GPS     │ │                 │ │ POST /sensors/heartbeat            │
│    (A7670E AT  │ │ 1. store to DB  │ │ → response bring 'commands'        │
│    +CGPSINFO)  │ │    (SQLite)     │ │ → _process_commands()              │
│ 2. local log   │ │ 2. POST         │ │   (endpoint 4 ACK, event-driven)   │
│ 3. POST        │ │    /sensors/    │ │                                    │
│    /sensors/   │ │    telemetry    │ │ Emergency Mode DOES NOT affect     │
│    location    │ │ → response bring│ │ interval Heartbeat at all          │
│                │ │   'config'      │ │                                    │
│ Emergency Mode │ │   (remote thr.) │ └────────────────────────────────────┘
│ DOES NOT       │ │                 │
│ affects        │ │ wake up         │ ┌────────────────────────────────────┐
│ at all         │ │ WHEN            │ │ FLUSH QUEUE                        │
│                │ │ Emergency mode  │ │                                    │
└────────────────┘ │ (_telemetry_    │ │ Interval: 120s (independen)        │
                   │  wake Event)    │ │ Retry offline queue FIFO           │
                   └─────────────────┘ │ (api_queue di SQLite)              │
                                       │ Stop when disconnect again,        │
                                       │ maintain FIFO  order               │
                                       └────────────────────────────────────┘
                                       ┌────────────────────────────────────┐
                                       │ RETENTION                          │
                                       │                                    │
                                       │ Interval: 6 jam                    │
                                       │ Purge sensor_readings +            │
                                       │ api_queue (selesai) +              │
                                       │ location_log lama (> 3 days)       │
                                       └────────────────────────────────────┘
```

## 4 Endpoint API
| # | Endpoint | Scheduler | Interval | note |
|---|----------|-----------|----------|---------|
| 1 | `POST /sensors/location` | Location Publisher | 1800s (tetap) | GPS ONLY taken here |
| 2 | `POST /sensors/telemetry` | Telemetry Publisher | 1800s / 600s (emergency) | Response bring `config` (remote threshold), data is stored in SQLite first |
| 3 | `POST /sensors/heartbeat` | Heartbeat Publisher | 300s (tetap) | Response bring `commands` |
| 4 | `POST /sensors/commands/ack` | Event-driven dari #3 | — | only run if response #3 bring `commands` |

---

## data flow (penting)

1. **read** all sensor every `EF\WS_READ_INTERVAL` second.
2. **Store to SQLite first** (`sensor_readings`, local source of truth) —
   will not lose data even if connection is off/dead.
3. **local evaluation** to `config/thresholds.json` — ONLY used to turn on siren in real-time 
    on field. Hasil evaluasi ini
   **does not** store to database or sending to API — alarm level &
   threshold "resmi" is backend responsibility, not device.
4. **try sending** payload to `EFWS_API_URL/sensors/telemetry`. if success
   , finish. if failed (signal dead), payload automativally send to
   offline qeue (`api_queue`) — payload store AS IS, doesnt change.
5. when offline, publisher **does not** spam retry — only chek signal 
   every `EFWS_CONNECTIVITY_CHECK_SEC` (default 120s / 2 menit). when
   online again, every qeue in-flush automatically regulary FIFO.
```
read all sensor → count waterlevel  → evaluasi threshold (remote-first per-field)
     ↓                                         ↓
Update _latest_data                   Is there a threshold exceeded?
(dibaca Publisher)                         ↓              ↓
                                        YA: N times      TIDAK:
                                        series?            ↓
                                         ↓           _emergency.clear()
                                         ↓           alarm.set_level("normal")
                                      _emergency.set()
                                      alarm.set_level("critical")
                                      _telemetry_wake.set()   ← wake Telemetry NOW
                                      _emergency_immediate_send.set()  ← only once
```
### Telemetry Publisher (Thread)
```
wait _telemetry_wake or interval finished
     ↓
get _latest_data snapshot (lock)
     ↓
count rainfall_delta (delta from previous delivery, no from 1 hour  window sensor)
     ↓
store to SQLite First (sensor_readings + full_payload for audit)
     ↓
POST /sensors/telemetry
     ├── Sukses → apply remote_config (threshold override per-field)
     └── fail (network/5xx) → enter api_queue (FIFO), di-flush seperate thread 
```

### GPS — Location Publisher
```
Priority fallback (tiap 1800s):
  1. AT+CGNSSPWR=1 → polling AT+CGPSINFO → fix? → source="gps"
  2. Semua percobaan gagal & pernah fix sebelumnya → source="gps_cached" (posisi terakhir)
  3. Belum pernah fix sama sekali → source="config" (koordinat statis dari .env)
```

### Emergency Mode
- **enter:** N consecutive readings through threshold → `_emergency.set()` → wake when  Telemetry Publisher
  (Immediate Emergency Send), then change interval to 600s
- **out:** all values returnto normal → `_emergency.clear()` → interval back to 1800s
- **doesnt effect:** Location Publisher and Heartbeat Publisher (fixed interval)

### Threshold — Remote-first Per-field
```
resolve_active_thresholds(local, remote_config):
  every field: remote wins if not None, else use lokal
  windDangerThreshold → ALWAYS lokal (not in API contract)
```

## Offline Queue flow

```
Connection/5xx failed → payload goes into api_queue (SQLite, FIFO)
        ↓
Flush Queue thread (every 120s):
  Check connection → online?
  → YA: flush batch 10 item FIFO
       Sukses  → mark sent=1
       4xx     → mark failed (throw away, dont block FIFO)
       failed again  → stop at that item , maintain FIFO 
  → NO: skip (tunggu 120s lagi)

Item is skiped after failing 10x (stale, dont block FIFO forever).
api_queue (those with sent=1 or attempts≥10) are cleared by thread retention every 6 hours.
```

---
## Module responsibilities


| Module | main File | responsibilites |
|--------|-----------|---------------|
| **sensors/** | `bme280.py`, `pressure.py`,`yf-w201.py`, `JSN_SR04T.py`, `anemometer.py`, `wind_direction.py`, `battery.py`, `flame.py`, `rainfall.py`,  | Driver hardware, each have `.read()` → dict. `null_sensor.py` for fallback if sensor fail init. `mock_sensors.py` for `EFWS_RUN_MODE=mock`. |
| **alarm/** | `relay.py`, `siren.py` | `relay.py`: driver GPIO low-level. `AlarmController`: 2 level eskalasi (WARNING=pulsing 0.4s/1.6s, CRITICAL=on terus) from 1 relay. No separate buzzer. |
| **communication/** | `sim_detector.py`, `a7670e.py`, `sim7600_legacy.py`, `api_publisher.py` | Auto-detect modul 4G (A7670E atau SIM7600 via ATI fingerprint, cache ke `.sim_cache`). `api_publisher.py`: the only data exit route (REST + offline queue). |
| **database/** | `db_manager.py` | SQLite: tabel `sensor_readings`, `api_queue`, `location_log`. Does not store alarm levels / threshold — that's the backend's responsibility. |
| **config/** | `settings.py`, `thresholds.json`, `threshold_resolver.py` | `settings.py`: semua env var tersentral. `thresholds.json`: local fallback ONLY for real-time siren. `threshold_resolver.py`: merge remote+lokal per-field. |
| **main.py** | — | Orchestrator: inisialize all module, run 6 thread, sensor sampling main loop. |

---

## Design Principles

- **Data is never lost:** SQLite is written BEFORE sending to the API. Failed sending → offline queue → automatic retry.
- **Real-time, network-independent siren:** Local threshold evaluation and relay run on the main thread, never waiting for an API response.
- **Remote-first threshold:** The backend can override per-field thresholds via telemetry responses. The device always has a local fallback.
- **Emergency does not affect Location/Heartbeat:** only the Telemetry interval changes during an emergency.
- **Sensor failure graceful:** Failed sensor init → `NullSensor` (return `None` for all fields) → `_exceeds(None, ...)` is always False → no false alarms.
- **SIM auto-detect:** A single code running on the A7670E or SIM7600, automatically selected at startup based on ATI responses.