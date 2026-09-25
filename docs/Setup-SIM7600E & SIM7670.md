# README — Setup SIM7600E as connection Main Raspberry Pi

Dokumen this contains tutorial setup **SIM7600E-H 4G LTE modem** on **Raspberry Pi 4** so that become connection internet main, while **WiFi become connection backup**.

Final goal:

```text
SIM7600E 4G = connection main
WiFi        = connection backup / fallback automatically
```

if modem SIM7600E removed, Raspberry Pi automatically again using WiFi. if modem installed again, Raspberry Pi will trying again using connection 4G.

---

## 1. Hardware that used

- Raspberry Pi 4
- SIM7600E-H 4G HAT / USB modem
- SIM card active
- Antenna LTE
- Cable USB data
- Power supply Raspberry Pi that stabil
- connection WiFi as backup

> Note important: modem 4G must connected to Raspberry Pi through **USB data**. GPIO only usually NOT enough so that modem appear as device internet.

---

## 2. check power Raspberry Pi

before setup modem, check whether Raspberry Pi mengalami undervoltage:

```bash
vcgencmd get_throttled
```

Target ideal:

```text
throttled=0x0
```

if appear:

```text
throttled=0x50000
```

this means Raspberry Pi ever mengalami undervoltage sejak boot. Use power supply that more stabil, minimal:

```text
5V 3A berkualitas
more safe 5V 4A–5A if modem ikut used
```

Modem 4G can draw current enough large when searching network.

---

## 3. check modem detected by USB

Colok modem SIM7600E to port USB Raspberry Pi, then Run:

```bash
lsusb
```

The target is to appear device like:

```text
ID 1e0e:9001 Qualcomm / Option SimTech
```

or terdapat Name:

```text
SIMCom
Qualcomm
```

Then check port serial:

```bash
ls /dev/ttyUSB*
```

Target:

```text
/dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyUSB2 /dev/ttyUSB3 /dev/ttyUSB4
```

if not yet appear, try:

```text
1. Replace cable USB, make sure cable data
2. Press tombol PWRKEY / POWER modem 2–3 seconds
3. Move port USB
4. Use power supply that more strong
5. Try powered USB hub
```

for melihat log when modem dicolok:

```bash
sudo dmesg -wH
```

Then cabut-colok modem and see whether appear log `new USB device`, `SIMCom`, or `ttyUSB`.

Exit from log:

```text
CTRL + C
```

---

## 4. Install NetworkManager and ModemManager

Install manual:

```bash
sudo apt update
sudo apt install -y modemmanager network-manager
```

Enable service:

```bash
sudo systemctl enable --now ModemManager
sudo systemctl enable --now NetworkManager
```

Restart service:

```bash
sudo systemctl restart ModemManager
sudo systemctl restart NetworkManager
```

Reboot so that bersih:

```bash
sudo reboot
```

---

## 5. check ModemManager detecting modem

After Raspberry Pi on again:

```bash
mmcli -L
```

Example result that correct:

```text
/org/freedesktop/ModemManager1/Modem/0 [QUALCOMM INCORPORATED] SIMCOM_SIM7600E-H
```

check status device NetworkManager:

```bash
nmcli device status
```

Example:

```text
DEVICE         TYPE      STATE         CONNECTION
wlan0          wifi      connected     netplan-wlan0-Uwaterloo
cdc-wdm0       gsm       disconnected  --
eth0           ethernet  unavailable   --
```

if `cdc-wdm0` appear as `gsm`, this means modem ready configured with a connection.

---

## 6. Do not use AT manual when using NetworkManager

if previously using Minicom and run:

```text
AT+NETOPEN
AT+CGACT
AT+HTTPINIT
```

should stop first use of AT manual for connection internet.

NetworkManager + ModemManager will configuring connection modem in a automatically.

If still exists Minicom open:

```text
CTRL + A
X
Yes
```

or turn off from terminal:

```bash
sudo killall minicom 2>/dev/null
sudo killall picocom 2>/dev/null
```

---

## 7. For connection 4G manual

for APN, many provider Indonesia can using:

```text
internet
```

Including AXIS/XL, Telkomsel/by.U, and several Indosat.

For connection:

```bash
sudo nmcli connection add type gsm ifname cdc-wdm0 con-name "EWS-4G" apn "internet"
```

if profile already exists, enough update:

```bash
sudo nmcli connection modify "EWS-4G" gsm.apn "internet"
```

Set 4G as connection main:

```bash
sudo nmcli connection modify "EWS-4G" \
  connection.autoconnect yes \
  connection.autoconnect-priority 100 \
  ipv4.method auto \
  ipv4.route-metric 50 \
  ipv6.method ignore
```

Enable connection 4G:

```bash
sudo nmcli connection up "EWS-4G"
```

---

## 8. Make WiFi as backup

see Name connection WiFi:

```bash
nmcli connection show
```

Example Name WiFi:

```text
netplan-wlan0-Uwaterloo
```

Set WiFi as backup with route metric larger:

```bash
sudo nmcli connection modify "netplan-wlan0-Uwaterloo" \
  connection.autoconnect yes \
  connection.autoconnect-priority 0 \
  ipv4.route-metric 600 \
  ipv6.route-metric 600
```

> Replace `netplan-wlan0-Uwaterloo` according to Name WiFi that appear in Raspberry Pi kamu.

---

## 9. check connection main already through modem

Run:

```bash
nmcli device status
```

Target:

```text
cdc-wdm0       gsm       connected      EWS-4G
wlan0          wifi      connected      netplan-wlan0-Uwaterloo
```

check route internet:

```bash
ip route get 8.8.8.8
```

if 4G already become main, the result usually shows interface modem, for example:

```text
dev wwan0
```

or interface sejenis from modem.

if still shows:

```text
dev wlan0
```

means WiFi still become route main and route metric need checked again.

Tes ping:

```bash
ping -c 4 8.8.8.8
```

---

## 10. Script automatically setup connection 4G main + WiFi backup

Script this **NOT menginstall package**. Install `network-manager` and `modemmanager` must performed manual like section previously.

For file:

```bash
nano ~/ews_network_setup.sh
```

Content:

```bash
#!/bin/bash

set -e

CONNECTION_NAME="EWS-4G"
MODEM_METRIC=50
WIFI_METRIC=600
DEFAULT_APN="internet"

echo "======================================"
echo " EWS Network Setup - 4G Main + WiFi Backup"
echo " without install package"
echo "======================================"

if [ "$EUID" -ne 0 ]; then
  echo "[ERROR] Run with sudo:"
  echo "sudo bash ~/ews_network_setup.sh"
  exit 1
fi

echo "[1/7] check service ModemManager and NetworkManager..."

if ! systemctl is-active --quiet ModemManager; then
  echo "[WARN] ModemManager not active yet. Enabling..."
  systemctl enable --now ModemManager
fi

if ! systemctl is-active --quiet NetworkManager; then
  echo "[WARN] NetworkManager not active yet. Enabling..."
  systemctl enable --now NetworkManager
fi

echo "[OK] Service active."

sleep 3

echo "[2/7] Deteksi modem..."

MODEM_ID=$(mmcli -L 2>/dev/null | grep -oP 'Modem/\K[0-9]+' | head -n 1 || true)

if [ -z "$MODEM_ID" ]; then
  echo "[WARN] Modem not yet detected by ModemManager."
  echo "[WARN] Script still continue creating profile 4G."
  echo "[WARN] If nanti modem installed, NetworkManager will try auto-connect."
  OPERATOR_CODE=""
else
  echo "[OK] Modem found: Modem/$MODEM_ID"

  echo "[INFO] Enable modem..."
  mmcli -m "$MODEM_ID" --enable || true

  sleep 3

  OPERATOR_CODE=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null | grep "modem.3gpp.operator-code" | cut -d: -f2 | tr -d ' ' || true)

  echo "[INFO] Operator code: ${OPERATOR_CODE:-unknown}"
fi

echo "[3/7] Determine APN based on provider..."

case "$OPERATOR_CODE" in
  "51010")
    PROVIDER="Telkomsel / by.U"
    APN="internet"
    ;;
  "51011")
    PROVIDER="XL / AXIS"
    APN="internet"
    ;;
  "51001")
    PROVIDER="Indosat"
    APN="internet"
    ;;
  "51021")
    PROVIDER="Indosat / IM3"
    APN="internet"
    ;;
  "51089")
    PROVIDER="Tri"
    APN="3data"
    ;;
  *)
    PROVIDER="Unknown / Default"
    APN="$DEFAULT_APN"
    ;;
esac

echo "[INFO] Provider : $PROVIDER"
echo "[INFO] APN      : $APN"

echo "[4/7] For or update connection 4G..."

if nmcli connection show "$CONNECTION_NAME" >/dev/null 2>&1; then
  echo "[INFO] Profile $CONNECTION_NAME already exists. Update setting..."
else
  echo "[INFO] Creating profile $CONNECTION_NAME..."
  nmcli connection add type gsm ifname "*" con-name "$CONNECTION_NAME" apn "$APN"
fi

nmcli connection modify "$CONNECTION_NAME" \
  gsm.apn "$APN" \
  connection.autoconnect yes \
  connection.autoconnect-priority 100 \
  ipv4.method auto \
  ipv4.route-metric "$MODEM_METRIC" \
  ipv6.method ignore

echo "[5/7] Set all connection WiFi as backup..."

WIFI_CONNECTIONS=$(nmcli -t -f NAME,TYPE connection show | grep ":802-11-wireless" | cut -d: -f1 || true)

if [ -z "$WIFI_CONNECTIONS" ]; then
  echo "[WARN] There is no profile WiFi found."
else
  echo "$WIFI_CONNECTIONS" | while read -r WIFI_NAME; do
    if [ -n "$WIFI_NAME" ]; then
      echo "[INFO] Set WiFi backup: $WIFI_NAME"
      nmcli connection modify "$WIFI_NAME" \
        connection.autoconnect yes \
        connection.autoconnect-priority 0 \
        ipv4.route-metric "$WIFI_METRIC" \
        ipv6.route-metric "$WIFI_METRIC" || true
    fi
  done
fi

echo "[6/7] Enable connection 4G..."

nmcli connection down "$CONNECTION_NAME" >/dev/null 2>&1 || true
sleep 2
nmcli connection up "$CONNECTION_NAME" || true

echo "[7/7] FINAL STATUS..."

echo ""
echo "======================================"
echo " MODEM"
echo "======================================"
mmcli -L || true

echo ""
echo "======================================"
echo " DEVICE STATUS"
echo "======================================"
nmcli device status || true

echo ""
echo "======================================"
echo " CONNECTION LIST"
echo "======================================"
nmcli connection show || true

echo ""
echo "======================================"
echo " IP ROUTE"
echo "======================================"
ip route || true

echo ""
echo "======================================"
echo " ROUTE TO INTERNET"
echo "======================================"
ip route get 8.8.8.8 || true

echo ""
echo "======================================"
echo " PING TEST"
echo "======================================"
ping -c 4 8.8.8.8 || true

echo ""
echo "======================================"
echo " finished"
echo "======================================"
echo "Target:"
echo "- if modem installed and konek: internet through 4G"
echo "- if modem dicabut: automatically fallback to WiFi"
echo "- if modem installed again: automatically behind to 4G"
echo ""
echo "check manual:"
echo "ip route get 8.8.8.8"
echo ""
echo "If through modem usually appear:"
echo "dev wwan0 / ppp0 / usb0"
echo ""
echo "If through WiFi appear:"
echo "dev wlan0"
```

Save:

```text
CTRL + O
ENTER
CTRL + X
```

Make executable:

```bash
chmod +x ~/ews_network_setup.sh
```

Run:

```bash
sudo bash ~/ews_network_setup.sh
```

---

## 11. Test fallback automatically

### when modem installed

```bash
ip route get 8.8.8.8
```

Target:

```text
dev wwan0
```

or interface modem sejenis.

### Cabut modem

Wait 30–60 seconds, then:

```bash
ip route get 8.8.8.8
```

Target:

```text
dev wlan0
```

### Pasang modem again

Wait 60 seconds, then:

```bash
ip route get 8.8.8.8
```

Target:

```text
dev wwan0
```

---

## 12. Test speed connection modem

Install speedtest:

```bash
sudo apt update
sudo apt install -y speedtest-cli
```

Run:

```bash
speedtest-cli --simple
```

check first route so that speedtest correct-correct through modem:

```bash
ip route get 8.8.8.8
```

if still through WiFi, do not assume result speedtest as result SIM7600E.

---

## 13. Remote SSH remote

for access SSH remote through network 4G, recommended using **Tailscale** because connection cellular usually located in behind CGNAT.

Install Tailscale in Raspberry Pi:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

check IP Tailscale Raspberry Pi:

```bash
tailscale ip -4
```

SSH from laptop:

```bash
ssh uwfadmin@IP_TAILSCALE_RASPBERRY_PI
```

Example:

```bash
ssh uwfadmin@100.77.65.15
```

---

## 14. Troubleshooting

### A. `mmcli -L` displaying `No modems were found`

check:

```bash
lsusb
ls /dev/ttyUSB*
```

if modem NOT appear in `lsusb`, the problem is in hardware:

```text
1. Cable USB not cable data
2. Modem not yet ON / PWRKEY not yet pressed
3. Power insufficient
4. Port USB faulty
5. Modem ONLY connected to GPIO, not USB
```

### B. `cdc-wdm0 gsm disconnected`

This means modem detected, but connection not yet was created/active.

Run:

```bash
sudo nmcli connection up "EWS-4G"
```

### C. Route still through WiFi

check metric:

```bash
ip route
```

Make sure metric modem more small from WiFi:

```text
4G  metric 50
WiFi metric 600
```

Update again:

```bash
sudo nmcli connection modify "EWS-4G" ipv4.route-metric 50
sudo nmcli connection modify "NAMA_WIFI" ipv4.route-metric 600
```

### D. Internet modem NOT running

check status modem:

```bash
mmcli -m 0
```

check device:

```bash
nmcli device status
```

Try restart service:

```bash
sudo systemctl restart ModemManager
sudo systemctl restart NetworkManager
sudo mmcli -S
sudo nmcli connection up "EWS-4G"
```

---

## 15. Ringkasan command important

```bash
# check power
vcgencmd get_throttled

# check USB modem
lsusb
ls /dev/ttyUSB*

# check modem
mmcli -L

# check device network
nmcli device status

# For connection 4G
sudo nmcli connection add type gsm ifname cdc-wdm0 con-name "EWS-4G" apn "internet"

# Set 4G main
sudo nmcli connection modify "EWS-4G" \
  connection.autoconnect yes \
  connection.autoconnect-priority 100 \
  ipv4.method auto \
  ipv4.route-metric 50 \
  ipv6.method ignore

# Set WiFi backup
sudo nmcli connection modify "NAMA_WIFI" \
  connection.autoconnect yes \
  connection.autoconnect-priority 0 \
  ipv4.route-metric 600 \
  ipv6.route-metric 600

# Enable 4G
sudo nmcli connection up "EWS-4G"

# check route main
ip route get 8.8.8.8

# Test internet
ping -c 4 8.8.8.8
```

---

## 16. Structure connection final

```text
Raspberry Pi 4
├── SIM7600E-H 4G modem
│   ├── APN: internet
│   ├── Profile: EWS-4G
│   └── Route metric: 50
│
└── WiFi backup
    ├── Profile: netplan-wlan0-Uwaterloo / Name WiFi other
    └── Route metric: 600
```

with configuration this, Raspberry Pi will prioritize modem 4G for internet, while WiFi still available as backup.
