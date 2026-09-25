#!/bin/bash
# =============================================================================
# EWS GSM Auto Connect (v2)
# =============================================================================
# Perubahan main from versi sebelumnya:
#   1. Menunggu modem BENAR-BENAR teregistrasi ke jaringan operator (3GPP
#      attach), not only menunggu modem detected oleh ModemManager.
#   2. `nmcli connection up` dicoba beberapa kali (retry+backoff), dan
#      each attempt diverifikasi with mengecek default route correct2
#      through interface modem -- not asal exit 0.
#   3. All langkah kritikal dicatat with status jelas (OK/WARN/FAIL)
#      dan timestamp, none lagi `|| true` that membungkam kegagalan.
#   4. Dicek juga status SIM (locked/PIN) so that if SIM ke-lock, itu
#      directly kelihatan di log alih-alih diam-diam failed connect.
#   5. Exit code skrip TETAP selalu 0 di akhir (see section "EXIT POLICY"
#      di bawah) -- ini SENGAJA dipertahankan sama seperti versi old,
#      so that efws.service (that memakai Requires=gsm-connect.service)
#      tetap start walau GSM failed total, dan EFWS bisa jalan use
#      offline queue / WiFi backup. That berubah not exit code-nya,
#      tapi APAKAH GSM correct-correct connect or not sekarang tercatat
#      jelas di journal (journalctl -u gsm-connect).
# =============================================================================

set -u

CONNECTION_NAME="EWS-4G"
DEFAULT_APN="internet"
MODEM_METRIC=50
WIFI_METRIC=600

MODEM_WAIT_ATTEMPTS=30       # tunggu modem detected: 30 x 2s = 60s
REGISTRATION_WAIT_ATTEMPTS=30 # tunggu attach ke jaringan: 30 x 2s = 60s
CONNECT_ATTEMPTS=4            # attempt nmcli connection up
CONNECT_RETRY_DELAY=5         # jeda antar attempt (seconds)

# -----------------------------------------------------------------------
# Logging helper -- all log punya timestamp + level, enter ke journald
# through StandardOutput=journal di service file, jadi bisa dilihat with:
#   journalctl -u gsm-connect -b
# -----------------------------------------------------------------------
log() {
    local level="$1"; shift
    printf '[EWS-GSM][%s] %s: %s\n' "$(date '+%H:%M:%S')" "$level" "$*"
}

log INFO "Starting GSM auto connect..."

systemctl is-active --quiet ModemManager || systemctl start ModemManager
systemctl is-active --quiet NetworkManager || systemctl start NetworkManager

nmcli radio wwan on || log WARN "Failed mengaktifkan radio wwan (mungkin sudah on)"

# Create GSM connection profile if not exists
if ! nmcli connection show "$CONNECTION_NAME" >/dev/null 2>&1; then
    log INFO "Membuat profil GSM new: $CONNECTION_NAME"
    if ! nmcli connection add type gsm ifname "*" con-name "$CONNECTION_NAME" apn "$DEFAULT_APN"; then
        log FAIL "Failed membuat profil GSM. Check apakah plugin NetworkManager-gsm installed."
    fi
fi

# -----------------------------------------------------------------------
# STEP 1: Tunggu modem detected oleh ModemManager
# -----------------------------------------------------------------------
MODEM_ID=""
for i in $(seq 1 "$MODEM_WAIT_ATTEMPTS"); do
    MODEM_ID=$(mmcli -L 2>/dev/null | grep -oP 'Modem/\K[0-9]+' | head -n1 || true)
    if [ -n "$MODEM_ID" ]; then
        log INFO "Modem detected: ID=$MODEM_ID (attempt $i)"
        break
    fi
    log INFO "Menunggu modem detected... ($i/$MODEM_WAIT_ATTEMPTS)"
    sleep 2
done

if [ -z "$MODEM_ID" ]; then
    log FAIL "Modem Not detected after $((MODEM_WAIT_ATTEMPTS*2))s. Check connection USB/serial modem."
    log WARN "Melanjutkan without GSM -- sistem akan bergantung pada WiFi (if ada)."
fi

APN="$DEFAULT_APN"
PROVIDER="Unknown"
REGISTERED=false

if [ -n "$MODEM_ID" ]; then

    if ! mmcli -m "$MODEM_ID" --enable >/dev/null 2>&1; then
        log WARN "mmcli --enable failed or modem sudah enabled, lanjut check status."
    fi
    sleep 3

    # -- Check status SIM (locked / missing) so that kegagalan SIM not
    #    ketutup diam-diam seperti sebelumnya.
    SIM_STATUS=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null | grep "modem.generic.state" | cut -d= -f2 | tr -d ' ' || true)
    if [ "$SIM_STATUS" = "locked" ]; then
        log FAIL "Modem dalam status 'locked' -- possibly SIM needs PIN. GSM not akan bisa connect sampai ini dibereskan manual (mmcli -m $MODEM_ID --pin=XXXX)."
    fi

    OPERATOR_CODE=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null | grep "modem.3gpp.operator-code" | cut -d= -f2 | tr -d ' ' || true)

    case "$OPERATOR_CODE" in
        "51010") PROVIDER="Telkomsel / by.U"; APN="internet" ;;
        "51011") PROVIDER="XL / AXIS";        APN="internet" ;;
        "51001") PROVIDER="Indosat";          APN="internet" ;;
        "51021") PROVIDER="Indosat / IM3";    APN="internet" ;;
        "51089") PROVIDER="Tri";              APN="3data"    ;;
        *)       PROVIDER="Default";          APN="$DEFAULT_APN" ;;
    esac

    log INFO "Provider detected : $PROVIDER (operator-code: ${OPERATOR_CODE:-unknown})"
    log INFO "APN that used    : $APN"

    # -------------------------------------------------------------------
    # STEP 2: Tunggu modem BENAR-BENAR attach ke jaringan operator.
    # Ini section that HILANG di versi old -- versi old only menunggu
    # modem "detected", lalu directly nmcli connection up. Padahal
    # antara "modem detected" dan "modem attach ke jaringan seluler"
    # (registration-state = home/roaming) bisa needs 10-40 seconds lagi,
    # terutama if signal lemah. If nmcli up dipanggil before ini
    # complete, ia gampang timeout -- dan versi old membungkam error itu
    # with `|| true` sehingga kelihatan "successful" padahal not.
    # -------------------------------------------------------------------
    for i in $(seq 1 "$REGISTRATION_WAIT_ATTEMPTS"); do
        REG_STATE=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null | grep "modem.3gpp.registration-state" | cut -d= -f2 | tr -d ' ' || true)
        if [ "$REG_STATE" = "home" ] || [ "$REG_STATE" = "roaming" ]; then
            log INFO "Modem teregistrasi ke jaringan operator (state: $REG_STATE), attempt $i"
            REGISTERED=true
            break
        fi
        log INFO "Menunggu registrasi ke jaringan seluler... state when ini: ${REG_STATE:-unknown} ($i/$REGISTRATION_WAIT_ATTEMPTS)"
        sleep 2
    done

    if [ "$REGISTERED" = false ]; then
        log FAIL "Modem not successful attach ke jaringan operator dalam $((REGISTRATION_WAIT_ATTEMPTS*2))s. Signal mungkin lemah or SIM bermasalah."
    fi
fi

# -----------------------------------------------------------------------
# Configure GSM connection profile (metric low = prioritas main)
# -----------------------------------------------------------------------
nmcli connection modify "$CONNECTION_NAME" \
    gsm.apn "$APN" \
    connection.autoconnect yes \
    connection.autoconnect-priority 100 \
    ipv4.method auto \
    ipv4.route-metric "$MODEM_METRIC" \
    ipv6.method ignore \
    || log FAIL "Failed memodifikasi profil connection $CONNECTION_NAME"

# -----------------------------------------------------------------------
# Configure WiFi as backup (metric high = prioritas low, TAPI tetap
# auto-connect so that used if GSM failed total). Section ini TIDAK
# needs WiFi for ada -- if none profil WiFi tersimpan, loop di
# bawah only jalan atas daftar empty dan not melakukan apa-apa. Jadi
# ketiadaan WiFi TIDAK menghalangi langkah-langkah GSM di atas maupun di
# bawah sama sekali.
# -----------------------------------------------------------------------
WIFI_CONNECTIONS=$(nmcli -t -f NAME,TYPE connection show | grep ":802-11-wireless" | cut -d: -f1 || true)

if [ -z "$WIFI_CONNECTIONS" ]; then
    log INFO "None profil WiFi tersimpan -- lanjut only with GSM."
else
    echo "$WIFI_CONNECTIONS" | while read -r WIFI_NAME; do
        if [ -n "$WIFI_NAME" ]; then
            log INFO "Set WiFi sebagai backup: $WIFI_NAME"
            nmcli connection modify "$WIFI_NAME" \
                connection.autoconnect yes \
                connection.autoconnect-priority 0 \
                ipv4.route-metric "$WIFI_METRIC" \
                ipv6.route-metric "$WIFI_METRIC" \
                || log WARN "Failed memodifikasi profil WiFi $WIFI_NAME"
        fi
    done
fi

# -----------------------------------------------------------------------
# STEP 3: Connect GSM with retry, dan VERIFIKASI hasilnya real --
# not only "nmcli exit 0" tapi correct-correct check default route through
# interface modem. Ini juga section that hilang di versi old.
# -----------------------------------------------------------------------
GSM_CONNECTED=false

for attempt in $(seq 1 "$CONNECT_ATTEMPTS"); do
    log INFO "Menghubungkan GSM... attempt $attempt/$CONNECT_ATTEMPTS"

    if nmcli connection up "$CONNECTION_NAME" >/dev/null 2>&1; then
        GSM_IFACE=$(nmcli -g GENERAL.DEVICES connection show "$CONNECTION_NAME" 2>/dev/null | head -n1)
        ROUTE_INFO=$(ip route get 8.8.8.8 2>/dev/null || true)

        if [ -n "$GSM_IFACE" ] && echo "$ROUTE_INFO" | grep -q "dev $GSM_IFACE"; then
            log INFO "GSM connected. Default route terkonfirmasi through interface $GSM_IFACE."
            GSM_CONNECTED=true
            break
        else
            log WARN "nmcli melaporkan sukses tapi default route BELUM through interface GSM ($GSM_IFACE). Mungkin masih tertahan WiFi metric or belum dapat IP."
        fi
    else
        log WARN "nmcli connection up failed pada attempt $attempt."
    fi

    if [ "$attempt" -lt "$CONNECT_ATTEMPTS" ]; then
        sleep "$CONNECT_RETRY_DELAY"
    fi
done

if [ "$GSM_CONNECTED" = true ]; then
    log INFO "STATUS AKHIR: GSM/SIM successful connect dan jadi jalur main."
else
    log FAIL "STATUS AKHIR: GSM/SIM FAILED connect after $CONNECT_ATTEMPTS attempt."
    if [ -n "$WIFI_CONNECTIONS" ]; then
        log WARN "Sistem akan mengandalkan WiFi sebagai fallback (if WiFi successful connect)."
    else
        log WARN "None WiFi backup available -- possibly NONE konektivitas internet sama sekali. EFWS akan jalan with offline queue."
    fi
fi

log INFO "Current route:"
ip route get 8.8.8.8 2>&1 || log WARN "Cannot resolve route ke 8.8.8.8 -- possibly belum ada connection internet sama sekali."

log INFO "Done."

# =============================================================================
# EXIT POLICY (SENGAJA, jangan diubah without update efws.service juga):
# Skrip ini SELALU exit 0, walau GSM_CONNECTED=false. Ini konsisten
# with versi old, sesuai dependency `efws.service` that use
# `Requires=gsm-connect.service`. If skrip ini exit non-zero, systemd
# akan MEMBLOKIR efws.service sama sekali -- padahal EFWS punya
# offline-queue dan tetap berguna running local walau without internet.
# That membedakan from versi old: sekarang status sukses/failed GSM
# TERCATAT JELAS di journal, not lagi dibungkam oleh `|| true`.
# =============================================================================
exit 0