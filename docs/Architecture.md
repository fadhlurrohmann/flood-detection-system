# Flood runtime and API contract

The runtime loads pressure, rainfall, ultrasonic distance, water flow, battery voltage, BME280, wind speed, and wind direction. Soil, flame, and a separate buzzer are not loaded. A failed driver is replaced with a null sensor and its error is logged.

## Runtime

1. The sampling loop reads all eight sensors, validates measurements, evaluates local alarms, and logs every cycle. Pressure loop faults invalidate pressure depth. Missing ultrasonic echoes never reuse an old sample.
2. Pressure depth and calibrated ultrasonic depth trigger at or above the water threshold. Without a mounting-height calibration, the raw-distance threshold triggers at or below its limit. Configured pressure, temperature, humidity, and wind thresholds are evaluated too; flow is alarmed only if a flow threshold is configured. Local alarms wait for the required consecutive dangerous readings and silence on a normal cycle.
3. Hourly rainfall drives the rainfall alarm. The API's rainfall value is a different quantity: rain since the preceding durably queued telemetry report.
4. First/routine/emergency reporting queues location, telemetry, and heartbeat together in SQLite. A single upload worker owns the HTTP session, preserving offline request bodies and queue order. GPS and retention use separate workers; neither GPS nor HTTP delays local alarm evaluation.
5. Remote nonnegative finite numeric thresholds override local values. Null or malformed fields fall back locally. The newer pressureDepthDangerThreshold name is accepted alongside the legacy waterDangerThreshold.
6. The rainfall baseline and queued bundle commit in the same transaction. Payload construction alone never advances the baseline. Restarts retain it; failed transactions roll back both requests and state. The first report without a baseline sends zero, missing rainfall sends null, and a reset cumulative counter produces zero for that interval.
7. Network errors, HTTP 408/429, and 5xx responses remain pending. Permanent HTTP rejection or malformed queue JSON marks that row discarded. A crash after server acceptance but before local confirmation can replay a request: delivery is at least once.
8. Ctrl+C or SIGTERM silences/releases the alarm and sensors, wakes workers, and closes resources. Already-running GPS/HTTP calls have bounded timeouts; a daemon worker may still be returning during process exit.

## Payload contract retained from main

Each request carries deviceId and deviceToken. The telemetry value is a list of records with exactly these keys:

| Key | Meaning |
|---|---|
| timestamp | Sampling timestamp in UTC, ending in Z |
| bme_temp_c | BME280 temperature in degrees Celsius |
| bme_humidity_pct | BME280 relative humidity percentage |
| bme_pressure_hpa | BME280 atmospheric pressure in hPa |
| sps_depth_m | Pressure-sensor depth in metres; never replaced by ultrasonic depth |
| sps_pressure_bar | Pressure-sensor pressure in bar |
| wind_speed_ms | Wind speed in metres per second |
| wind_dir | Compass abbreviation such as N or NE |
| flow_lpm | Average litres per minute since the previous sample |
| distance_m | Fresh ultrasonic distance in metres |
| battery_pct | Linear voltage-based percentage, clamped to 0-100 |
| rainfall | Millimetres since the preceding durably queued report, from the cumulative counter |

No camelCase telemetry aliases or extra voltage/hourly-rain/flow-total fields are added to the wire contract. Those measurements remain in local SQLite. Faults produce JSON null rather than fabricated zero measurements.

Location retains latitude and longitude. Heartbeat retains batteryLevel. Command ACK retains commandId, status, and error. Endpoints remain /sensors/location, /sensors/telemetry, /sensors/heartbeat, and /sensors/commands/ack under EFWS_API_URL.

The working sensor-removal runtime's bundled report timing is retained; main's broken independent publisher implementation is not reintroduced. The normal default interval is 360 seconds, with immediate reports on dangerous cycles.

## Database compatibility

Startup additively upgrades either branch's sensor_readings table without deleting historical columns or rows. Both older water_* columns and main's sps_* columns are maintained. BME, wind, voltage, flow totals, hourly/cumulative rain, errors, and exact telemetry snapshots are stored. location_log preserves position reporting history. runtime_state holds each device's rainfall baseline. Retention removes old readings, location history, and finished requests while preserving pending uploads and baseline state.

Existing pending payloads are replayed unchanged, including older formats. Verify that the production backend still accepts them during rollout.

## Deployment notes

Configure different serial devices for RS485 wind speed, UART wind direction, and modem AT access. The modem detector skips configured wind ports, including symlink aliases. The default 12 pulses/litre flow calibration and 1 mm hourly rainfall limit come from main; verify them against the actual meter and site requirements. High-water alarm direction and consecutive confirmation come from the working sensor-removal branch.

The modem's GNSS is still handled by Python's GPS worker. Do not run a shell GPS reader concurrently on the same AT port. Modem/network setup scripts remain separate from the application.

The repository has no production backend schema. Local tests verify field names, missing data, HTTP receipt, migrations, and queue behavior; actual hardware calibration and production persistence still require Pi/backend acceptance testing.

Queued heartbeat replies process commands and queue ACKs. Reboot schedules an efws.service restart; SUCCESS acknowledges scheduling rather than completion. Mock mode simulates it.
