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
│ BME280
| SEN0460 (AQI)│         |      Raspberry Pi 4        │           └────────────┘
├──────────────┤  SPI    │      (main.py orchestrator)│
│              │◄───────►│                            │   GPIO I  ┌────────────┐
│  MCP3008 ADC │         │                            │◄──────────│ JSN-SR04T  │
│ (Pressure/   │         │                            │           │ YF-S201    │
│              │         │                            │           │  (digital) │
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

## Database compatibility

### AQI integration

`AQISensor` wraps the existing SEN0460 I2C helpers and rolling ISPU calculation in `sensors/aqi.py`. The main factory loads it as `aqi` in hardware mode and `MockAQI` in mock mode. Warm-up and failed/invalid readings become null without stopping the other drivers. AQI does not change the local siren rules.

Every telemetry record now also includes `pm1`, `pm25`, `pm10` (ug/m3), `aqi` (the existing ISPU-style index), and `aqi_provisional` (boolean, null when unavailable). These extend the existing payload without renaming its fields. The index uses rolling PM2.5/PM10 samples, not PM1 or only the latest measurement. The default window is 24 hours in memory and restarts with the process. The provisional flag describes elapsed window time from the first valid sample; it is not a guarantee of continuous samples or regulatory validation.

SQLite additively gains `aqi_pm1`, `aqi_pm25`, `aqi_pm10`, `aqi`, and `aqi_provisional`. Historical rows remain unchanged with null in these new columns. Full payload snapshots and offline queue entries retain the same AQI values that were prepared for transmission. The backend must accept the five additional telemetry fields.

Startup additively upgrades either branch's sensor_readings table without deleting historical columns or rows. Both older water_* columns and main's sps_* columns are maintained. BME, wind, voltage, flow totals, hourly/cumulative rain, errors, and exact telemetry snapshots are stored. location_log preserves position reporting history. runtime_state holds each device's rainfall baseline. Retention removes old readings, location history, and finished requests while preserving pending uploads and baseline state.

Existing pending payloads are replayed unchanged, including older formats. Verify that the production backend still accepts them during rollout.

## Deployment notes

Configure different serial devices for RS485 wind speed, UART wind direction, and modem AT access. The modem detector skips configured wind ports, including symlink aliases. The default 12 pulses/litre flow calibration and 1 mm hourly rainfall limit come from main; verify them against the actual meter and site requirements. High-water alarm direction and consecutive confirmation come from the working sensor-removal branch.

The modem's GNSS is still handled by Python's GPS worker. Do not run a shell GPS reader concurrently on the same AT port. Modem/network setup scripts remain separate from the application.

The repository has no production backend schema. Local tests verify field names, missing data, HTTP receipt, migrations, and queue behavior; actual hardware calibration and production persistence still require Pi/backend acceptance testing.

Queued heartbeat replies process commands and queue ACKs. Reboot schedules an efws.service restart; SUCCESS acknowledges scheduling rather than completion. Mock mode simulates it.
