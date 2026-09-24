# README — Setup SIM7600E sebagai connection Utama Raspberry Pi

Dokumen ini berisi tutorial setup **SIM7600E-H 4G LTE modem** pada **Raspberry Pi 4** agar menjadi connection internet utama, sedangkan **WiFi menjadi connection backup**.

Target akhir:

```text
SIM7600E 4G = connection utama
WiFi        = connection cadangan / fallback automatically
```

if modem SIM7600E dilepas, Raspberry Pi automatically kembali memakai WiFi. if modem dipasang lagi, Raspberry Pi akan mencoba kembali memakai connection 4G.

---

## 1. Hardware that digunakan

- Raspberry Pi 4
- SIM7600E-H 4G HAT / USB modem
- SIM card aktif
- Antena LTE
- Kabel USB data
- Power supply Raspberry Pi that stabil
- connection WiFi sebagai backup

> Catatan penting: modem 4G must tersambung ke Raspberry Pi melalui **USB data**. GPIO saja biasanya NOT cukup agar modem appear sebagai device internet.

---

## 2. check power Raspberry Pi

before setup modem, check apakah Raspberry Pi mengalami undervoltage:

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

artinya Raspberry Pi pernah mengalami undervoltage sejak boot. Gunakan power supply that lebih stabil, minimal:

```text
5V 3A berkualitas
lebih aman 5V 4A–5A if modem ikut dipakai
```

Modem 4G can menarik arus cukup besar when mencari jaringan.

---

## 3. check modem terdeteksi oleh USB

Colok modem SIM7600E ke port USB Raspberry Pi, lalu Run:

```bash
lsusb
```

Targetnya appear device seperti:

```text
ID 1e0e:9001 Qualcomm / Option SimTech
```

or terdapat nama:

```text
SIMCom
Qualcomm
```

Lalu check port serial:

```bash
ls /dev/ttyUSB*
```

Target:

```text
/dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyUSB2 /dev/ttyUSB3 /dev/ttyUSB4
```

if not yet appear, coba:

```text
1. Ganti kabel USB, pastikan kabel data
2. Tekan tombol PWRKEY / POWER modem 2–3 detik
3. Pindah port USB
4. Gunakan power supply that lebih kuat
5. Coba powered USB hub
```

for melihat log when modem dicolok:

```bash
sudo dmesg -wH
```

Lalu cabut-colok modem and see apakah appear log `new USB device`, `SIMCom`, or `ttyUSB`.

Keluar from log:

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

Aktifkan service:

```bash
sudo systemctl enable --now ModemManager
sudo systemctl enable --now NetworkManager
```

Restart service:

```bash
sudo systemctl restart ModemManager
sudo systemctl restart NetworkManager
```

Reboot agar bersih:

```bash
sudo reboot
```

---

## 5. check ModemManager mendeteksi modem

After Raspberry Pi nyala lagi:

```bash
mmcli -L
```

Contoh hasil that benar:

```text
/org/freedesktop/ModemManager1/Modem/0 [QUALCOMM INCORPORATED] SIMCOM_SIM7600E-H
```

check status device NetworkManager:

```bash
nmcli device status
```

Contoh:

```text
DEVICE         TYPE      STATE         CONNECTION
wlan0          wifi      connected     netplan-wlan0-Uwaterloo
cdc-wdm0       gsm       disconnected  --
eth0           ethernet  unavailable   --
```

if `cdc-wdm0` appear sebagai `gsm`, artinya modem siap dibuatkan connection.

---

## 6. Jangan pakai AT manual when memakai NetworkManager

if sebelumnya memakai Minicom and menjalankan:

```text
AT+NETOPEN
AT+CGACT
AT+HTTPINIT
```

sebaiknya hentikan dulu penggunaan AT manual for connection internet.

NetworkManager + ModemManager akan mengatur connection modem secara automatically.

If masih ada Minicom terbuka:

```text
CTRL + A
X
Yes
```

or matikan from terminal:

```bash
sudo killall minicom 2>/dev/null
sudo killall picocom 2>/dev/null
```

---

## 7. Buat connection 4G manual

for APN, banyak provider Indonesia can memakai:

```text
internet
```

Termasuk AXIS/XL, Telkomsel/by.U, and several Indosat.

Buat connection:

```bash
sudo nmcli connection add type gsm ifname cdc-wdm0 con-name "EWS-4G" apn "internet"
```

if profile already ada, cukup update:

```bash
sudo nmcli connection modify "EWS-4G" gsm.apn "internet"
```

Set 4G sebagai connection utama:

```bash
sudo nmcli connection modify "EWS-4G" \
  connection.autoconnect yes \
  connection.autoconnect-priority 100 \
  ipv4.method auto \
  ipv4.route-metric 50 \
  ipv6.method ignore
```

Aktifkan connection 4G:

```bash
sudo nmcli connection up "EWS-4G"
```

---

## 8. Jadikan WiFi sebagai backup

see nama connection WiFi:

```bash
nmcli connection show
```

Contoh nama WiFi:

```text
netplan-wlan0-Uwaterloo
```

Set WiFi sebagai backup with route metric lebih besar:

```bash
sudo nmcli connection modify "netplan-wlan0-Uwaterloo" \
  connection.autoconnect yes \
  connection.autoconnect-priority 0 \
  ipv4.route-metric 600 \
  ipv6.route-metric 600
```

> Ganti `netplan-wlan0-Uwaterloo` sesuai nama WiFi that appear di Raspberry Pi kamu.

---

## 9. check connection utama already lewat modem

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

if 4G already menjadi utama, hasilnya biasanya menunjukkan interface modem, misalnya:

```text
dev wwan0
```

or interface sejenis from modem.

if masih menunjukkan:

```text
dev wlan0
```

berarti WiFi masih menjadi jalur utama and route metric need dicek ulang.

Tes ping:

```bash
ping -c 4 8.8.8.8
```

---

## 10. Script automatically setup connection 4G utama + WiFi backup

Script ini **NOT menginstall package**. Install `network-manager` and `modemmanager` must dilakukan manual seperti bagian sebelumnya.

Buat file:

```bash
nano ~/ews_network_setup.sh
```

Isi:

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
  echo "[WARN] ModemManager not yet aktif. Mengaktifkan..."
  systemctl enable --now ModemManager
fi

if ! systemctl is-active --quiet NetworkManager; then
  echo "[WARN] NetworkManager not yet aktif. Mengaktifkan..."
  systemctl enable --now NetworkManager
fi

echo "[OK] Service aktif."

sleep 3

echo "[2/7] Deteksi modem..."

MODEM_ID=$(mmcli -L 2>/dev/null | grep -oP 'Modem/\K[0-9]+' | head -n 1 || true)

if [ -z "$MODEM_ID" ]; then
  echo "[WARN] Modem not yet terdeteksi oleh ModemManager."
  echo "[WARN] Script tetap lanjut membuat profile 4G."
  echo "[WARN] If nanti modem dipasang, NetworkManager akan coba auto-connect."
  OPERATOR_CODE=""
else
  echo "[OK] Modem found: Modem/$MODEM_ID"

  echo "[INFO] Enable modem..."
  mmcli -m "$MODEM_ID" --enable || true

  sleep 3

  OPERATOR_CODE=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null | grep "modem.3gpp.operator-code" | cut -d: -f2 | tr -d ' ' || true)

  echo "[INFO] Operator code: ${OPERATOR_CODE:-unknown}"
fi

echo "[3/7] Tentukan APN berdasarkan provider..."

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

echo "[4/7] Buat or update connection 4G..."

if nmcli connection show "$CONNECTION_NAME" >/dev/null 2>&1; then
  echo "[INFO] Profile $CONNECTION_NAME already ada. Update setting..."
else
  echo "[INFO] Membuat profile $CONNECTION_NAME..."
  nmcli connection add type gsm ifname "*" con-name "$CONNECTION_NAME" apn "$APN"
fi

nmcli connection modify "$CONNECTION_NAME" \
  gsm.apn "$APN" \
  connection.autoconnect yes \
  connection.autoconnect-priority 100 \
  ipv4.method auto \
  ipv4.route-metric "$MODEM_METRIC" \
  ipv6.method ignore

echo "[5/7] Set semua connection WiFi sebagai backup..."

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

echo "[6/7] Aktifkan connection 4G..."

nmcli connection down "$CONNECTION_NAME" >/dev/null 2>&1 || true
sleep 2
nmcli connection up "$CONNECTION_NAME" || true

echo "[7/7] Status akhir..."

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
echo " ROUTE KE INTERNET"
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
echo "- if modem installed and konek: internet lewat 4G"
echo "- if modem dicabut: automatically fallback ke WiFi"
echo "- if modem dipasang lagi: automatically balik ke 4G"
echo ""
echo "check manual:"
echo "ip route get 8.8.8.8"
echo ""
echo "If lewat modem biasanya appear:"
echo "dev wwan0 / ppp0 / usb0"
echo ""
echo "If lewat WiFi appear:"
echo "dev wlan0"
```

Save:

```text
CTRL + O
ENTER
CTRL + X
```

Jadikan executable:

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

Tunggu 30–60 detik, lalu:

```bash
ip route get 8.8.8.8
```

Target:

```text
dev wlan0
```

### Pasang modem lagi

Tunggu 60 detik, lalu:

```bash
ip route get 8.8.8.8
```

Target:

```text
dev wwan0
```

---

## 12. Test kecepatan connection modem

Install speedtest:

```bash
sudo apt update
sudo apt install -y speedtest-cli
```

Run:

```bash
speedtest-cli --simple
```

check dulu route agar speedtest benar-benar lewat modem:

```bash
ip route get 8.8.8.8
```

if masih lewat WiFi, jangan anggap hasil speedtest sebagai hasil SIM7600E.

---

## 13. Remote SSH jarak jauh

for akses SSH jarak jauh melalui jaringan 4G, recommended memakai **Tailscale** because connection seluler biasanya berada di balik CGNAT.

Install Tailscale di Raspberry Pi:

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

Contoh:

```bash
ssh uwfadmin@100.77.65.15
```

---

## 14. Troubleshooting

### A. `mmcli -L` menampilkan `No modems were found`

check:

```bash
lsusb
ls /dev/ttyUSB*
```

if modem NOT appear di `lsusb`, masalahnya di hardware:

```text
1. Kabel USB bukan kabel data
2. Modem not yet ON / PWRKEY not yet ditekan
3. Power kurang
4. Port USB bermasalah
5. Modem ONLY connected ke GPIO, bukan USB
```

### B. `cdc-wdm0 gsm disconnected`

Artinya modem terdeteksi, tapi connection not yet dibuat/aktif.

Run:

```bash
sudo nmcli connection up "EWS-4G"
```

### C. Route masih lewat WiFi

check metric:

```bash
ip route
```

Pastikan metric modem lebih kecil from WiFi:

```text
4G  metric 50
WiFi metric 600
```

Update lagi:

```bash
sudo nmcli connection modify "EWS-4G" ipv4.route-metric 50
sudo nmcli connection modify "NAMA_WIFI" ipv4.route-metric 600
```

### D. Internet modem NOT jalan

check status modem:

```bash
mmcli -m 0
```

check device:

```bash
nmcli device status
```

Coba restart service:

```bash
sudo systemctl restart ModemManager
sudo systemctl restart NetworkManager
sudo mmcli -S
sudo nmcli connection up "EWS-4G"
```

---

## 15. Ringkasan command penting

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

# Buat connection 4G
sudo nmcli connection add type gsm ifname cdc-wdm0 con-name "EWS-4G" apn "internet"

# Set 4G utama
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

# Aktifkan 4G
sudo nmcli connection up "EWS-4G"

# check route utama
ip route get 8.8.8.8

# Test internet
ping -c 4 8.8.8.8
```

---

## 16. Struktur connection final

```text
Raspberry Pi 4
├── SIM7600E-H 4G modem
│   ├── APN: internet
│   ├── Profile: EWS-4G
│   └── Route metric: 50
│
└── WiFi backup
    ├── Profile: netplan-wlan0-Uwaterloo / nama WiFi lain
    └── Route metric: 600
```

with configuration ini, Raspberry Pi akan memprioritaskan modem 4G for internet, sedangkan WiFi tetap tersedia sebagai backup.
