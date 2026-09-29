# Flood Early Warning System (EFWS)

IoT-based Flood Early Warning System using Raspberry Pi 4.

## Features

- Dual Soil Moisture Monitoring (surface + deep probe)
- Water Level Monitoring (submersible pressure sensor, 4-20mA loop)
- Rainfall Monitoring (DFRobot SEN0575)
- Ultrasonic Distance Monitoring (JSN-SR04T)
- 4G Communication (A7670E or SIM7600, auto-detected)
- REST API telemetry with local offline queue (SQLite) — data always
  saved locally first, sent immediately, auto-retried every 2 minutes
  while offline
- Local Alarm System (relay + siren, real-time — not network dependent)
- Solar Powered Operation

## Hardware

- Raspberry Pi 4
- MCP3008 ADC (SPI)
- 1x Logic Level Converter (min. 6-channel)
- 2x Soil moisture probe (surface + deep)
- Submersible pressure sensor (4-20mA loop, water level)
- DFRobot SEN0575 rainfall sensor
- JSN-SR04T ultrasonic distance sensor
- A7670E or SIM7600 4G LTE HAT (only one installed at a time)
- LiFePO4 Battery
- Solar Panel
- Relay + Siren (local alarm)

See `docs/Pinout.md` for full wiring reference.

## Run on a Desktop (Mock Mode)

Mock mode requires no Raspberry Pi hardware and is the default when no `.env`
file is present.

```powershell
python -m pip install -r requirements-mock.txt
python tools/mock_api_server.py
```

Keep that terminal open. In a second PowerShell terminal, run:

```powershell
python main.py
```

Press `Ctrl+C` to stop. To run exactly one cycle, set the optional environment
variable before starting:

```powershell
$env:EFWS_MAX_CYCLES = "1"
python main.py
```

For Raspberry Pi hardware deployment, copy `.env.example` to `.env`, change
`EFWS_RUN_MODE=hardware`, configure the wiring values, and install
`requirements.txt`.

## Project Structure

```text
efws/
├── sensors/        # sensor drivers + mock_sensors.py for testing without hardware
├── communication/  # SIM auto-detect, REST API publisher (offline queue)
├── database/       # SQLite local logger + offline queue
├── alarm/          # relay/siren controller
├── config/         # settings.py + thresholds.json (local siren triggering only)
├── docs/           # Pinout, Architecture, Deployment guides
├── tests/          # per-component + integration tests
├── logs/
└── main.py
```
