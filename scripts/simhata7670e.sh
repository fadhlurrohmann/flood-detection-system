#!/bin/bash

# ============================================================
# EFWS — Network Setup (SIMCom A7670E RNDIS + GPS Fetch)
#
# Alur:
#   1. Pastikan NetworkManager aktif
#   2. Deteksi interface RNDIS (eth1 / usb0) dari A7670E
#   3. Konfigurasi/Aktifkan dhclient pada interface RNDIS
#   4. Set Wi-Fi sebagai backup (metric lebih besar)
#   5. Verifikasi IP & default route ke A7670E
#   6. GPS fetch via AT+CGNSSPWR=1 + AT+CGNSSINFO (3 percobaan)
#      Hasil disimpan ke GPS_CACHE_FILE untuk dibaca main.py
#
# Script selalu exit 0 → tidak pernah memblokir efws.service.
# ============================================================

set -u

# ── Konfigurasi ─────────────────────────────────────────────
MODEM_METRIC=500
WIFI_METRIC=600

# Port AT command SIM A7670E (biasanya /dev/ttyUSB1 atau /dev/ttyUSB2)
SIM_AT_PORT="${EFWS_SIM_PORT:-/dev/ttyUSB1}"
SIM_BAUD="${EFWS_SIM_BAUD:-115200}"

# GPS Config (Sintaks A7670E: CGNSSPWR / CGNSSINFO)
GPS_ATTEMPTS=3
GPS_WARMUP_FIRST=90      # detik warm-up sebelum percobaan 1
GPS_POLL_INTERVAL=5      # detik antar pembacaan AT+CGNSSINFO
GPS_POLL_TIMEOUT=60      # detik maks polling per percobaan
GPS_RETRY_WAIT=120       # detik tunggu antar percobaan jika gagal

# Lokasi cache GPS
GPS_CACHE_FILE="${EFWS_GPS_CACHE:-/tmp/ews_gps_cache.json}"

# Modem wait
MODEM_WAIT_ATTEMPTS=30
MODEM_WAIT_DELAY=2

# Log
LOG_DIR="/home/uwfadmin/ews/logs"
LOG_FILE="${LOG_DIR}/network_setup.log"
mkdir -p "$LOG_DIR"

# ── Helper logging ───────────────────────────────────────────
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$msg" | tee -a "$LOG_FILE"
}

log_gps() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [GPS] $*"
    echo "$msg" | tee -a "$LOG_FILE"
}

# ── Helper: set WiFi sebagai backup ─────────────────────────
set_wifi_backup() {
    local found=0
    while IFS=: read -r cname ctype; do
        if [ "$ctype" = "802-11-wireless" ] && [ -n "$cname" ]; then
            nmcli connection modify "$cname" \
                connection.autoconnect yes \
                connection.autoconnect-priority 0 \
                ipv4.route-metric "$WIFI_METRIC" \
                ipv6.route-metric "$WIFI_METRIC" \
                2>/dev/null || true
            log "WiFi backup: $cname (metric $WIFI_METRIC)"
            found=1
        fi
    done < <(nmcli -t -f NAME,TYPE connection show 2>/dev/null)
    [ "$found" -eq 0 ] && log "Tidak ada profil WiFi ditemukan."
}

# ── Helper: parse AT+CGNSSINFO → JSON (Sintaks A7670E) ───────
# Format: +CGNSSINFO: [mode],[gps_sv],[glonass_sv],[beidou_sv],[lat],[N/S],[lon],[E/W],[date],[time],[alt],[speed],[course]
# Contoh fix:   +CGNSSINFO: 2,05,00,00,0114.5506,S,11649.5982,E,270826,173042.0,8.2,0.0,0.0
# Contoh no fix: +CGNSSINFO: ,,,,,,,,,,,,
parse_cgnssinfo() {
    local raw="$1"
    local line

    line=$(echo "$raw" | grep -oE '\+CGNSSINFO:[^\r\n]+' | head -n1 || true)
    if [ -z "$line" ]; then
        echo ""
        return 1
    fi

    local data
    data=$(echo "$line" | sed 's/+CGNSSINFO:[[:space:]]*//')

    # Cari lat_raw & lat_ns berdasarkan field yang ada
    local lat_raw lat_ns lon_raw lon_ew date_raw utc_raw alt spd crs

    # Field A7670E berisi indikator satelit di depan
    lat_raw=$(echo "$data" | cut -d, -f5 | tr -d ' ')
    if [ -z "$lat_raw" ]; then
        # Fallback jika format keluaran langsung ke lat tanpa SV count
        lat_raw=$(echo "$data" | cut -d, -f1 | tr -d ' ')
        if [ -z "$lat_raw" ]; then
            echo ""
            return 1
        fi
        lat_ns=$(echo  "$data" | cut -d, -f2)
        lon_raw=$(echo "$data" | cut -d, -f3)
        lon_ew=$(echo  "$data" | cut -d, -f4)
        date_raw=$(echo "$data" | cut -d, -f5)
        utc_raw=$(echo  "$data" | cut -d, -f6)
        alt=$(echo      "$data" | cut -d, -f7)
        spd=$(echo      "$data" | cut -d, -f8)
        crs=$(echo      "$data" | cut -d, -f9 | tr -d '[:space:]')
    else
        lat_ns=$(echo  "$data" | cut -d, -f6)
        lon_raw=$(echo "$data" | cut -d, -f7)
        lon_ew=$(echo  "$data" | cut -d, -f8)
        date_raw=$(echo "$data" | cut -d, -f9)
        utc_raw=$(echo  "$data" | cut -d, -f10)
        alt=$(echo      "$data" | cut -d, -f11)
        spd=$(echo      "$data" | cut -d, -f12)
        crs=$(echo      "$data" | cut -d, -f13 | tr -d '[:space:]')
    fi

    if [ -z "$lat_raw" ] || [ "$lat_raw" = "," ]; then
        echo ""
        return 1
    fi

    # Konversi NMEA ddmm.mmmm → desimal
    local lat lon
    lat=$(awk -v nmea="$lat_raw" -v dir="$lat_ns" '
        BEGIN {
            dot = index(nmea, ".")
            deg = substr(nmea, 1, dot - 3) + 0
            min = substr(nmea, dot - 2) + 0
            dd  = deg + min / 60.0
            if (dir == "S") dd = -dd
            printf "%.6f", dd
        }
    ')
    lon=$(awk -v nmea="$lon_raw" -v dir="$lon_ew" '
        BEGIN {
            dot = index(nmea, ".")
            deg = substr(nmea, 1, dot - 3) + 0
            min = substr(nmea, dot - 2) + 0
            dd  = deg + min / 60.0
            if (dir == "W") dd = -dd
            printf "%.6f", dd
        }
    ')

    local date_fmt utc_fmt
    if [ ${#date_raw} -eq 6 ]; then
        date_fmt="${date_raw:0:2}/${date_raw:2:2}/20${date_raw:4:2}"
    else
        date_fmt="$date_raw"
    fi
    if [ ${#utc_raw} -ge 6 ]; then
        utc_fmt="${utc_raw:0:2}:${utc_raw:2:2}:${utc_raw:4}"
    else
        utc_fmt="$utc_raw"
    fi

    printf '{"fix":true,"lat":%s,"lon":%s,"altitude_m":%s,"speed_kmh":%s,"course_deg":"%s","date_utc":"%s","time_utc":"%s","source":"gps","timestamp":%s}\n' \
        "$lat" "$lon" \
        "${alt:-null}" \
        "${spd:-null}" \
        "${crs:-0}" \
        "$date_fmt" \
        "$utc_fmt" \
        "$(date +%s)"
    return 0
}

# ── Helper: tulis cache GPS fallback ─────────────────────────
write_gps_cache_fallback() {
    local reason="$1"
    local ts
    ts=$(date +%s)
    cat > "$GPS_CACHE_FILE" <<EOF
{"fix":false,"lat":null,"lon":null,"reason":"${reason}","source":"none","timestamp":${ts}}
EOF
    log_gps "Cache ditulis (no fix): $reason"
}

# ── Helper: Cari port AT A7670E ──────────────────────────────
find_at_port() {
    local default_port="$1"
    local candidates="$default_port /dev/ttyUSB1 /dev/ttyUSB2 /dev/ttyUSB0"
    local checked=" "

    for p in $candidates; do
        if [ -z "$p" ] || [ ! -e "$p" ]; then continue; fi
        if echo "$checked" | grep -q " $p "; then continue; fi
        checked="$checked$p "

        fuser -k "$p" > /dev/null 2>&1 || true
        stty -F "$p" "$SIM_BAUD" raw -echo cs8 -cstopb -parenb 2>/dev/null || continue

        (
            exec 7<>"$p" || exit 1
            printf 'AT\r\n' >&7
            sleep 0.5
            resp=$(dd <&7 count=1 bs=512 iflag=nonblock 2>/dev/null || true)
            if echo "$resp" | grep -q "OK"; then exit 0; fi
            exit 1
        ) 2>/dev/null

        if [ $? -eq 0 ]; then
            echo "$p"
            return 0
        fi
    done

    echo ""
    return 1
}

# ── GPS fetch A7670E ─────────────────────────────────────────
gps_fetch() {
    local config_port="$1"
    local port

    log_gps "Mencari port AT A7670E yang bebas..."
    port=$(find_at_port "$config_port")

    if [ -z "$port" ]; then
        log_gps "Tidak ada port AT yang bebas. GPS skip."
        write_gps_cache_fallback "no_available_at_port"
        return 0
    fi

    log_gps "Menggunakan port AT: $port"

    stty -F "$port" "$SIM_BAUD" raw -echo cs8 -cstopb -parenb 2>/dev/null || {
        write_gps_cache_fallback "stty_failed"
        return 0
    }

    exec 7<>"$port" 2>/dev/null || {
        write_gps_cache_fallback "fd_open_failed"
        return 0
    }

    # Test AT dasar
    printf 'AT\r\n' >&7; sleep 0.5
    local at_resp
    at_resp=$(dd <&7 count=1 bs=512 iflag=nonblock 2>/dev/null || true)
    if ! echo "$at_resp" | grep -q "OK"; then
        log_gps "Modem tidak merespons AT."
        exec 7>&-
        write_gps_cache_fallback "modem_no_at_response"
        return 0
    fi

    # Nyalakan GNSS (A7670E spesifik: AT+CGNSSPWR=1)
    printf 'AT+CGNSSPWR=1\r\n' >&7; sleep 2
    local on_resp
    on_resp=$(dd <&7 count=1 bs=512 iflag=nonblock 2>/dev/null || true)
    log_gps "Power GNSS A7670E diaktifkan (AT+CGNSSPWR=1)."

    local attempt fix_found=0 gps_json=""

    for attempt in 1 2 3; do
        if [ "$attempt" -eq 1 ]; then
            log_gps "Percobaan $attempt/$GPS_ATTEMPTS: warm-up ${GPS_WARMUP_FIRST}s..."
            sleep "$GPS_WARMUP_FIRST"
        else
            log_gps "Percobaan $attempt/$GPS_ATTEMPTS: tunggu ${GPS_RETRY_WAIT}s..."
            sleep "$GPS_RETRY_WAIT"
        fi

        log_gps "Polling AT+CGNSSINFO..."

        local elapsed=0
        while [ "$elapsed" -lt "$GPS_POLL_TIMEOUT" ]; do
            dd <&7 count=1 bs=4096 iflag=nonblock > /dev/null 2>&1 || true

            # Query GNSS info khusus A7670E
            printf 'AT+CGNSSINFO\r\n' >&7
            sleep "$GPS_POLL_INTERVAL"

            local raw_resp
            raw_resp=$(dd <&7 count=1 bs=2048 iflag=nonblock 2>/dev/null || true)

            gps_json=$(parse_cgnssinfo "$raw_resp")
            if [ -n "$gps_json" ]; then
                log_gps "FIX ditemukan pada percobaan $attempt!"
                fix_found=1
                break 2
            fi

            elapsed=$(( elapsed + GPS_POLL_INTERVAL ))
            log_gps "  Belum fix (${elapsed}s/${GPS_POLL_TIMEOUT}s)..."
        done
    done

    exec 7>&-
    log_gps "Port AT ditutup."

    if [ "$fix_found" -eq 1 ]; then
        echo "$gps_json" > "$GPS_CACHE_FILE"
        log_gps "Cache GPS disimpan: $GPS_CACHE_FILE"
    else
        write_gps_cache_fallback "all_${GPS_ATTEMPTS}_attempts_failed"
    fi

    return 0
}

# ============================================================
# MAIN
# ============================================================
log "============================================================"
log "EFWS Network Setup SIMCom A7670E dimulai"

# ── Step 1: Cek NetworkManager ──────────────────────────────
log "[1/7] Cek NetworkManager..."
systemctl is-active --quiet NetworkManager || { log "Start NetworkManager..."; systemctl start NetworkManager; }
sleep 1

# ── Step 2: Cari Interface RNDIS A7670E (eth1 / usb0) ───────
log "[2/7] Menilai interface USB RNDIS (A7670E)..."
RNDIS_IFACE=""
for attempt in $(seq 1 "$MODEM_WAIT_ATTEMPTS"); do
    for iface in eth1 usb0 eth2; do
        if ip link show "$iface" >/dev/null 2>&1; then
            RNDIS_IFACE="$iface"
            break 2
        fi
    done
    log "  Menunggu interface USB RNDIS terdeteksi: $attempt/$MODEM_WAIT_ATTEMPTS ..."
    sleep "$MODEM_WAIT_DELAY"
done

if [ -z "$RNDIS_IFACE" ]; then
    log "PERINGATAN: Interface RNDIS (eth1/usb0) tidak ditemukan."
    write_gps_cache_fallback "modem_rndis_not_found"
    exit 0
fi

log "Interface RNDIS A7670E terdeteksi: $RNDIS_IFACE"

# ── Step 3: Alokasikan IP ke Interface RNDIS ─────────────
log "[3/7] Mengambil IP dari DHCP Modem ($RNDIS_IFACE)..."
if command -v dhclient >/dev/null 2>&1; then
    sudo dhclient -v "$RNDIS_IFACE" >> "$LOG_FILE" 2>&1 || true
else
    ip link set "$RNDIS_IFACE" up
fi
sleep 2

# Adjust route metric interface modem agar jadi prioritas utama
ip route add default via 192.168.0.1 dev "$RNDIS_IFACE" metric "$MODEM_METRIC" 2>/dev/null || \
ip route chg default via 192.168.0.1 dev "$RNDIS_IFACE" metric "$MODEM_METRIC" 2>/dev/null || true

# ── Step 4: Set WiFi sebagai backup ─────────────────────────
log "[4/7] Set WiFi sebagai backup..."
set_wifi_backup

# ── Step 5: Verifikasi Koneksi ───────────────────────────────
log "[5/7] Verifikasi koneksi internet $RNDIS_IFACE..."
if ping -I "$RNDIS_IFACE" -c 2 www.google.com >/dev/null 2>&1; then
    log "✓ Koneksi 4G ($RNDIS_IFACE) terhubung ke internet."
else
    log "i Warning: Ping via $RNDIS_IFACE belum berhasil."
fi

log "Default route:"
ip route show default | tee -a "$LOG_FILE" | head -5

# ── Step 6: GPS Fetch A7670E ─────────────────────────────────
log "------------------------------------------------------------"
log "GPS FETCH A7670E — $GPS_ATTEMPTS percobaan"
log "------------------------------------------------------------"

gps_fetch "$SIM_AT_PORT"

log "============================================================"
log "EFWS Network Setup Selesai."
exit 0