# EFWS Architecture Overview

```
                         ┌─────────────────────────── ┐
                         │   Solar 80-100W + LiFePO4  │
                         │   + Voltage Sensor Module  │
                         └─────────────┬───────────── ┘
                                       5V/12V/loop
                                        │
┌──────────────┐   I2C   ┌─────────────▼───────────── ┐   GPIO O  ┌────────────┐
│              │◄───────►│                            │──────────►│ Relay 5V   │──►12V Siren
│ GY-MS5837    │         │      Raspberry Pi 4        │           └────────────┘
├──────────────┤  SPI    │      (main.py orchestrator)│
│LLC ->        │◄───────►│                            │   GPIO I  ┌────────────┐
│  MCP3008 ADC │         │                            │◄──────────│ JSN-SR04T  │
│ (Soil x2/    │         │                            │           │ YF-S201    │
│  Pressure/   │         │                            │           │  (digital) │
│  Battery)    │         │                            │           └────────────┘
└──────────────┘         │                            │
┌──────────────┐  USB    │                            │  USB/UART  ┌─────────────┐
│ RS485 (s/d   │◄───────►│                            │───────────►│ A7670E /    │──► 4G Network
│ Anemometer   │         │                            │            │ SIM7600     │
└──────────────┘         └─────────────┬──────────────┘            │ (one only) │
                                        │                          └─────────────┘
                          ┌─────────────┴──────────────┐
                          │ 1) Save to SQLite FIRST     │
                          │ 2) Evaluate locally (siren) │
                          │ 3) Try sending to REST API  │
                          │ 4) Failure → offline queue  │
                          └─────────────┬──────────────┘
                                        ▼
                    EWS_API_URL/sensors/telemetry (backend)
                    ── backend stores the alarm level and
                       the "official" threshold evaluation
```

## Data flow (important)

1. **Read** all sensors every `EFWS_READ_INTERVAL` seconds.
2. **Save to SQLite first** (`sensor_readings`, the local source of truth) —
   data is never lost even when the signal or connection is down.
3. **Evaluate locally** against `config/thresholds.json` — this is used ONLY
   to activate the field siren in actual time. The result is **not** stored in
   the database or sent to the API; the backend owns the official alarm level
   and threshold evaluation.
4. **Try to send** the payload to `EFWS_API_URL/sensors/telemetry`. If it
   succeeds, the cycle is complete. If it fails, the payload automatically
   enters the offline queue (`api_queue`) unchanged.
5. While offline, the publisher **does not** spam retries. It checks
   connectivity every `EFWS_CONNECTIVITY_CHECK_SEC` (default 120 seconds),
   then flushes the entire queue in FIFO order when back online.

## Module responsibilities

- **sensors/**: one driver class per physical sensor; each exposes `.read()`
  and returns a dict. `mock_sensors.py` provides a simulated version for
  testing without hardware (`EFWS_RUN_MODE=mock`).
- **alarm/**: `relay.py` is driver GPIO low-level; `siren.py`
  (`AlarmController`) turns it into two escalation levels (WARNING = slow pulse,
  CRITICAL = continuously on) through the same relay. This hardware has no
  separate buzzer.
- **communication/**: `sim_detector.py` auto-detect module 4G that installed
  (A7670E or SIM7600), and `api_publisher.py` is the only outbound data path
  (REST API + offline queue). This project does not use MQTT or Telegram.
- **database/**: `db_manager.py` storing each reading sensor raw +
  the exact API payload, and manages the offline queue. It does not store the
  alarm level or thresholds; that is the backend's responsibility.
- **config/**: `settings.py` centralizes all pin/channel/credentials;
  `thresholds.json` centralizes warning/critical limits for the LOCAL siren only.
- **main.py**: read → save to DB → evaluate locally (siren) → send/queue → repeat.
