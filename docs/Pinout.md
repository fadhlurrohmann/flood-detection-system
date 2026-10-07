# EFWS — Output & Wiring Reference

Final hardware:
**Raspberry Pi 4 · MCP3008 (SPI ADC 8-ch) · 1x Logic Level Converter (5V digital → GPIO only)
· BME280 (I2C)
· Submersible Pressure Sensor (4-20mA loop) · DC Voltage Sensor Module 0-25V (battery)
· RS485 Anemometer · A7670E OR SIM7600 (auto-detect, only one installed)
· 5V Relay · 12V Siren**

> There is no flame sensor in this hardware. There is no separate buzzer — a
> single relay + siren is enough (2 alarm escalation levels via pulsing vs.
> continuous-on pattern; see `alarm/siren.py`). Thresholds and alarm level
> decisions are evaluated locally ONLY to trigger the siren in real time — they
> are not stored in the local database because the official alarm evaluation occurs
> in the backend.

---

## 1. Raspberry Pi 4 — Pins Used (BCM Numbering)

| Function | GPIO (BCM) | Physical Pin | Notes |
|----------|------------|--------------|-------|
| SPI SCLK (MCP3008) | GPIO11 | Pin 23 | SPI clock |
| SPI MISO (MCP3008) | GPIO9  | Pin 21 | Data from MCP3008 |
| SPI MOSI (MCP3008) | GPIO10 | Pin 19 | Data to MCP3008 |
| SPI CE0  (MCP3008) | GPIO8  | Pin 24 | Chip select |
| I2C SDA (BME280)   | GPIO2  | Pin 3  | I2C data |
| I2C SCL (BME280)   | GPIO3  | Pin 5  | I2C clock |
| Siren Relay (output) | GPIO27 | Pin 13 | To 5V relay IN |
| Status LED (output, optional) | GPIO23 | Pin 16 | Heartbeat indicator |
| 5V Rail | — | Pin 2 & 4 | Power LLC HV (do not use this for high current) |
| 3.3V Rail | — | Pin 1 & 17 | Power LLC LV, MCP3008 VDD/VREF, BME280 |
| GND | — | Pin 6, 9, 14, 20, 25, 30, 34, 39 | Shared ground |

Enable interfaces:
```bash
sudo raspi-config
# Interface Options → SPI → Yes
# Interface Options → I2C → Yes
```

---
## 2. BME280 & Rainfall Sensors — I2C Wiring (ambient: temperature / humidity / pressure)

### BME280 (ambient: suhu / kelembaban / tekanan)
| Pin BME280 | Hubung ke |
|-----------|-----------|
| VIN | Pi 3.3V |
| GND | GND bersama |
| SCL | GPIO3 (Pin 5) |
| SDA | GPIO2 (Pin 3) |

Alamat I2C: `0x76` (atau `0x77` tergantung solder jumper modul).

### DFRobot Gravity Rainfall Sensor (SEN0575) — Tipping Bucket
| Pin sensor | Hubung ke |
|-----------|-----------|
| VCC | Pi 3.3V |
| GND | GND bersama |
| SCL | GPIO3 (Pin 5) — **sama seperti BME280** |
| SDA | GPIO2 (Pin 3) — **sama seperti BME280** |

Alamat I2C: `0x1D` (`RAINFALL_I2C_ADDRESS` di `config/settings.py`) —
**beda dari BME280 (`0x76`/`0x77`)**, jadi wiring paralel di bus I2C yang
sama aman, tidak perlu multiplexer.

```bash
i2cdetect -y 1     # should show 0x76 (or 0x77 if address differs)
python3 tests/test_bme280.py
```

---

## 3. MCP3008 — Wiring to Raspberry Pi

| MCP3008 Pin | Connect To | Notes |
|-------------|------------|-------|
| VDD (pin 16) | Pi 3.3V | **DO NOT USE 5V** |
| VREF (pin 15) | Pi 3.3V | ADC scale 0-3.3V = raw 0-1023 |
| AGND (pin 14) | Common GND | |
| CLK (pin 13)  | GPIO11 (SCLK) | |
| DOUT (pin 12) | GPIO9 (MISO)  | |
| DIN (pin 11)  | GPIO10 (MOSI) | |
| CS/SHDN (pin 10) | GPIO8 (CE0) | |
| DGND (pin 9)  | Common GND | |
| CH2-CH3 | See channel table below | Wired directly — **no LLC** |
| CH0, CH1, CH4-CH7 | Spare, not wired | |

Verification: `ls /dev/spidev*` → should show `/dev/spidev0.0`

---

## 4. MCP3008 Channel Map — analog inputs connect DIRECTLY (no LLC)

Every analog input must stay **below 3.3V** (MCP3008 VREF) and is wired **directly** to the
MCP3008. Scale a higher voltage down with a resistor divider — **never route an analog signal
through the LLC** (see "Why analog must not go through the LLC" below).

| Channel | Signal | Voltage at pin | Notes |
|---------|--------|----------------|-------|
| **CH2** | Pressure sensor (via **R_BURDEN** 100Ω) | 0.4-2.0V | Water level (4-20mA loop) |
| **CH3** | Voltage Sensor Module **S** | battery ÷ 5 (~2.6V, max ~2.9V) | Battery voltage |
| CH0, CH1, CH4-CH7 | *(spare / expansion)* | — | — |

### Logic Level Converter — 5V DIGITAL signals into Pi GPIO only

The LLC is only for **digital** (high/low) signals from 5V sensors going into Pi GPIO
(max 3.3V). It does not connect to the MCP3008.

| LLC | HV Side (5V) ← from sensor | LV Side (3.3V) → to | Notes |
|-----|---------------------------|---------------------|-------|
| HV-1 / LV-1 | YF-S201 signal (5V pulses) | Pi GPIO (`GPIO_YF`, default 16) | water flow digital |
| other channels | *(spare)* — e.g. JSN-SR04T ECHO if the sensor runs on 5V | Pi GPIO | measure the signal first: 5V → via LLC, ≤3.3V → direct |

**Why analog must not go through the LLC:** a typical BSS138 LLC board has a 10kΩ pull-up
on every pin — HV pins to 5V, LV pins to 3.3V. A digital signal only needs "high" or "low",
so the pull-ups don't matter there. An analog signal needs its exact voltage, and the
pull-ups change it:
- HV side: the pull-up drags the sensor voltage upward toward 5V.
- LV side: any input above ~1.8V comes out as 3.3V ("high"), and an idle LV pin also
  sits at 3.3V, so the exact voltage is lost.
- TXS0108E-type LLCs are worse: their outputs snap to 0V or 3.3V.

### LLC Module Wiring

```
LLC:
  HV  pin  ←── 5V  (from buck converter / Pi pin 2/4)
  LV  pin  ←── 3.3V (from Pi pin 1/17)
  GND HV   ←── common ground
  GND LV   ←── common ground
```

---

## 5. Sensor-by-Sensor Wiring Details

### YF-S201 (Water Flow Sensor)
| Sensor pin | Connect to |
|-----------|------------|
| VCC | 5V (directly from source) |
| GND | Common ground |
| AOUT | LLC **HV-1** → LV-1 → MCP3008 |

### Submersible Pressure Sensor — 4-20mA loop (Water Level)

This sensor is a **2-wire loop-powered device** (not a direct 0-5V sensor), so its wiring differs from other sensors: it requires a precise **burden resistor** to convert the loop current into a voltage readable by the ADC.

```
PSU 12-24V (+) ──────────► Sensor Loop V+
                                  │
                    Sensor (variable 4-20mA depending on pressure/depth)
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │  R_BURDEN = 100Ω 0.1%   │
                    │  (precision, low-drift)  │
                    └────────────┬────────────┘
                                 │ tap here →  0.4-2.0V
                                 ▼
                       MCP3008 CH2  (direct, NO LLC)
                                 │
PSU 12-24V (−) ──────────► common ground (after R_BURDEN)
```

| Point | Connect to |
|-------|------------|
| Loop V+ | PSU 12-24V (+) — **not** from Pi/buck converter 5V |
| Loop output (after sensor) | Top of R_BURDEN (100Ω, 0.1%) |
| Bottom of R_BURDEN | Common ground & PSU (−) |
| Sensor/R_BURDEN connection point | MCP3008 **CH2** directly (no LLC) |

**Why 100Ω?**
- 4mA × 100Ω = **0.4V** → "empty" level (0m)
- 20mA × 100Ω = **2.0V** → "full" level (`PRESSURE_RANGE_M` — adjust to your sensor datasheet)
- 2.0V max stays below the MCP3008 VREF (3.3V), so the signal goes straight to CH2 without the LLC.
  `EFWS_PRESSURE_BURDEN_OHM` in `.env` must match the installed resistor (default 100).

The conversion formula is in `sensors/pressure.py`. **Adjust** `EFWS_PRESSURE_RANGE_M`
in `.env` to match the physical sensor depth/pressure range (many variants: 0-5m,
0-10m, 0-20m). The API payload sends two values from this sensor: `waterLevel` (meters)
and `waterLevelCurrentMa` (raw loop current, useful for the backend to detect a loop break — a sudden drop to ~0mA means a broken cable, not empty water).

### DC Voltage Sensor Module 0-25V (Battery)

This module already includes an internal voltage divider (no need to build one yourself).

| Module pin | Connect to |
|------------|------------|
| IN+ | Battery+ terminal (12V LiFePO4 or similar) |
| IN− | Battery− **after the BMS (P−)** — not the raw cell negative (B−) |
| GND (output side) | Common ground |
| S (output = battery ÷ 5) | MCP3008 **CH3** directly |

S stays below 3.3V for any battery up to 16.5V (14.4V → 2.88V), so it connects to CH3 directly.

Formula: `V_battery = raw / 1023 × MCP3008_VREF × BATTERY_DIVIDER_RATIO` (default 5.0).
To calibrate, measure the battery and S with a multimeter and set
`EFWS_BATTERY_DIVIDER_RATIO = V_battery / V_S`. Calibrate `BATTERY_MAX_V` /
`BATTERY_MIN_V` in `.env` according to your battery specification (default 12.6V full,
9.0V empty, suitable for 3S LiFePO4 packs).

### RS485 Anemometer (Modbus RTU)
| Connection | Connect to |
|-----------|------------|
| A (D+) | USB-RS485 converter terminal A |
| B (D−) | USB-RS485 converter terminal B |
| VCC | 12V or 5V depending on unit datasheet |
| GND | Common ground |

USB-RS485 → Pi USB port → appears as `/dev/ttyUSB0`. **No LLC required.**

### A7670E OR SIM7600 (choose one)

No different wiring is required between them — **install only one module**,
`communication/sim_detector.py` will auto-detect which one is present
(`AT+CGNSSPWR` → A7670E, `AT+CGPS` → SIM7600) and the software adapts automatically.

| Connection | Details |
|-----------|---------|
| Power | Depends on the HAT board (usually 5V from the Pi or separate 3.7-4.2V Li-ion) |
| Data | USB to Pi — appears as one of several `/dev/ttyUSBx` |
| LTE antenna | Required |
| GNSS antenna | Required separately |
| SIM card | Install before power-on |

```bash
ls /dev/ttyUSB*
python3 tests/test_sim_detector.py   # confirm which modem is detected
```

### 5V Relay → 12V Siren

```
Control side (Pi 3.3V GPIO):          High-power side (12V):
  GPIO27 ──────────────► IN relay       Battery+ ─── relay COM
  5V     ──────────────► VCC relay            Relay NO ─── Siren (+)
  GND    ──────────────► GND relay            Siren (−) ─── Battery−
```

> ⚠️ The 12V siren line **must never** touch any Pi pin.
> There is no separate buzzer — this relay handles 2 escalation levels
> (WARNING = slow pulse, CRITICAL = constant on), see `alarm/siren.py`.

---

## 6. Complete Signal Block Diagram

```
Battery Sensor S (÷5, max ~2.9V, direct) ─────────────┐
Pressure via R_BURDEN (0.4-2.0V, direct) ─────────────┤
                                ▼
                     MCP3008 CH2-CH3  (SPI0)
                                │
BME280 (I2C direct) ─────────────┤
RS485 Anemometer (USB) ──────────┤
A7670E / SIM7600 (USB) ──────────┤
                                ▼
                       Raspberry Pi 4 — main.py
                       1) read all sensors
                       2) SAVE to SQLite first (sensor_readings)
                       3) local evaluation → siren (real-time, not stored)
                       4) try to send to API — fail? queue it (api_queue)
                       5) re-check signal every 2 minutes → auto-flush queue
                                │ GPIO27
                                ▼
                        5V Relay ──► 12V Siren
```

---

## 7. Power Supply for Each Load

| Load | Voltage | Source | Notes |
|------|---------|--------|-------|
| Raspberry Pi 4 | 5V | Buck converter output | Via GPIO pins 2/4 or USB-C |
| MCP3008 VDD/VREF | 3.3V | Pi 3.3V rail | |
| BME280 | 3.3V | Pi 3.3V rail | I2C direct, no LLC |
| LLC LV | 3.3V | Pi 3.3V rail | |
| LLC HV | 5V | Buck converter / Pi 5V rail | |
| Submersible pressure sensor | 12-24V (loop) | **Separate PSU**, not from Pi/buck 5V | Loop-powered |
| Voltage sensor module (battery) | Passive, tapped from Battery+/− | — | No separate supply needed |
| RS485 anemometer | 12V or 5V | According to unit datasheet | |
| A7670E/SIM7600 | 5V or 3.7-4.2V | According to HAT board | |
| Relay coil | 5V | Pi 5V rail | |
| Siren | 12V | Battery (via relay NO/COM) | |

---

## 8. Checklist Before First Power-On

```
[ ] SPI enabled (raspi-config → Interface → SPI)
[ ] I2C enabled (raspi-config → Interface → I2C)
[ ] Common ground: Pi, MCP3008, LLC, all sensors, relay, pressure PSU → one GND
    (incl. the battery voltage module's output − pin — without it CH3 floats and reads random values)
[ ] Battery sensor S connected directly to MCP3008 CH3
[ ] No wire from any LLC LV pin to the MCP3008 (idle LV pins sit at 3.3V)
[ ] MCP3008 VDD & VREF to 3.3V (not 5V)
[ ] R_BURDEN 100Ω installed correctly in the pressure sensor loop, tapped directly to MCP3008 CH2
[ ] Pressure sensor PSU isolated from Pi/buck converter 5V
[ ] Voltage sensor module taps directly to Battery+/− (not through relay)
[ ] 12V siren path only through relay COM/NO, never touching Pi pins
[ ] Only ONE module installed: A7670E OR SIM7600 (do not install both)
[ ] LTE + GNSS antennas installed
[ ] SIM card installed before turning on the module

Software verification:
[ ] ls /dev/spidev*    → /dev/spidev0.0 present
[ ] i2cdetect -y 1     → BME280 address appears (0x76/0x77)
[ ] ls /dev/ttyUSB*    → multiple ports present (modem + anemometer)
[ ] python3 tests/test_all_sensors.py     → all sensors OK
[ ] python3 tests/test_offline_queue_integrity.py → queue integrity OK
[ ] python3 tests/test_sim_detector.py    → SIM module identified
```
