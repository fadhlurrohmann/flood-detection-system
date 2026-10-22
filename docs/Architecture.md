# Flood runtime and API contract

The active sensors are pressure, rainfall, ultrasonic distance, water flow, and battery voltage. Soil, BME280, and wind are not loaded.

1. The main loop reads all five sensors. Failed readings become null, with an error stored separately. Pressure open-loop/out-of-range faults invalidate the depth.
2. Local flood evaluation compares pressure depth and calibrated ultrasonic depth against `waterDangerThreshold` (greater than or equal). Either can detect danger. Rainfall uses `rainfallDangerThreshold` against the last hour's rain, rather than lifetime accumulated rain. Valid numeric remote thresholds override local values per field; missing, null, negative, or malformed values fall back locally.
3. The siren remains off until `alarm.consecutive_readings_required` dangerous cycles. A cycle without a danger trigger turns it off and resets the streak. Missing measurements are unknown and do not trigger; sensor errors must be monitored independently.
4. Every cycle is saved in `sensor_readings`, including errors and the exact telemetry snapshot. The schema migration adds columns to existing databases and retains historical columns and rows.
5. A first/routine/emergency report atomically queues location, telemetry, and heartbeat in SQLite before waking the upload worker. Local alarms do not wait for GPS or HTTP.
6. One upload worker owns the HTTP session and retries queued rows in order. Successful rows are marked delivered. Network errors, 408, 429, and server errors remain pending; permanent HTTP rejections and malformed JSON are marked discarded for inspection. Retention removes old readings and finished queue rows, preserving pending uploads.
7. A separate GPS worker retains the configured/last known location if no fix is available. The initial report can use the configured location while GNSS acquires a fix.
8. SIGTERM or Ctrl+C stops the loop, silences/releases the relay and sensor GPIO, closes the shared ADC, and wakes background workers. Calls already in progress have bounded network/GPS timeouts; process exit may finish before a daemon worker returns.

## Payloads

Location, telemetry, heartbeat, and command ACK retain their existing endpoints under `EFWS_API_URL`. Each carries `deviceId` and `deviceToken`.

| Telemetry key | Meaning |
|---|---|
| timestamp | Reading timestamp in UTC, with Z suffix |
| waterLevel | Pressure-derived depth in metres; calibrated ultrasonic fallback if pressure is unavailable |
| waterLevelCurrentMa | Pressure loop current in mA, also useful to diagnose a broken loop |
| distanceM | Fresh ultrasonic distance in metres, or null on no echo/out of range |
| flowRateLpm | Average L/min since the last flow read |
| flowTotalLiters | Accumulated litres since process startup |
| rainfallTotalMm | SEN0575 lifetime accumulation since its reset |
| rainfallLastHour | SEN0575 one-hour rainfall in mm |
| batteryVoltage | Measured battery voltage after divider correction |
| batteryLevel | Linear voltage-based percentage, clamped to 0–100 |

Heartbeat also carries `batteryLevel`. No soil, BME280, wind, or flame values are sent. Faults are represented by null measurements, not fabricated zero values. Full fault messages are retained in local logs and the database.

The repository contains no production backend schema. Acceptance of these telemetry fields and nullable measurements needs verification against that backend; local tests verify the device payload and a local HTTP receiver only. Old pending queue payloads are replayed unchanged, including those produced by older versions.

Heartbeat responses from queued deliveries still execute commands and queue ACKs. Supported `Reboot` restarts `efws.service` after a delay; SUCCESS means scheduling succeeded, not completion. Mock mode simulates that command. Unsupported commands receive FAILED. HTTP delivery is at least once: a process crash after a server accepts a request but before SQLite records delivery may cause replay.

For SEN0575 register semantics see the [manufacturer driver](https://github.com/DFRobot/DFRobot_RainfallSensor/blob/master/DFRobot_RainfallSensor.cpp). The ultrasonic wrapper observes fresh GPIO Zero samples because its normal averaging queue ignores missing echoes; see [GPIO Zero source](https://gpiozero.readthedocs.io/en/stable/_modules/gpiozero/input_devices.html).
