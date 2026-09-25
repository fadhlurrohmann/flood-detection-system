#!/bin/bash
# =============================================================================
# EWS GSM Auto Connect (v2)
# =============================================================================
# Perubahan main from version previously:
#   1. Waiting modem ACTUALLY registered to network operator (3GPP
#      attach), not only waiting modem detected by ModemManager.
#   2. `nmcli connection up` is attempted several time (retry+backoff), and
#      each attempt diverifikasi with mengecek default route correct2
#      through interface modem -- not source exit 0.
#   3. All step kritikal recorded with status clear (OK/WARN/FAIL)
#      and timestamp, none again `|| true` that silences failure.
#   4. Checked also status SIM (locked/PIN) so that if SIM to-lock, that
#      directly kelihatan in log alih-alih diam-diam failed connect.
#   5. Exit code script STILL always 0 at the end (see section "EXIT POLICY"
#      below) -- this INTENTIONALLY retained same like version old,
#      so that efws.service (that using Requires=gsm-connect.service)
#      still start although GSM failed total, and EFWS can running use
#      offline queue / WiFi backup. That changes not exit code-nya,
#      but WHETHER GSM correct-correct connect or not now tercatat
#      clear in journal (journalctl -u gsm-connect).
# =============================================================================

set -u

CONNECTION_NAME="EWS-4G"
DEFAULT_APN="internet"
MODEM_METRIC=50
WIFI_METRIC=600

MODEM_WAIT_ATTEMPTS=30       # wait modem detected: 30 x 2s = 60s
REGISTRATION_WAIT_ATTEMPTS=30 # wait attach to network: 30 x 2s = 60s
CONNECT_ATTEMPTS=4            # attempt nmcli connection up
CONNECT_RETRY_DELAY=5         # jeda antar attempt (seconds)

# -----------------------------------------------------------------------
# Logging helper -- all log has timestamp + level, enter to journald
# through StandardOutput=journal in service file, therefore can dilihat with:
#   journalctl -u gsm-connect -b
# -----------------------------------------------------------------------
log() {
    local level="$1"; shift
    printf '[EWS-GSM][%s] %s: %s\n' "$(date '+%H:%M:%S')" "$level" "$*"
}

log INFO "Starting GSM auto connect..."

systemctl is-active --quiet ModemManager || systemctl start ModemManager
systemctl is-active --quiet NetworkManager || systemctl start NetworkManager

nmcli radio wwan on || log WARN "Failed enabling radio wwan (possible already on)"

# Create GSM connection profile if not exists
if ! nmcli connection show "$CONNECTION_NAME" >/dev/null 2>&1; then
    log INFO "Creating profile GSM new: $CONNECTION_NAME"
    if ! nmcli connection add type gsm ifname "*" con-name "$CONNECTION_NAME" apn "$DEFAULT_APN"; then
        log FAIL "Failed creating profile GSM. Check whether plugin NetworkManager-gsm installed."
    fi
fi

# -----------------------------------------------------------------------
# STEP 1: Wait modem detected by ModemManager
# -----------------------------------------------------------------------
MODEM_ID=""
for i in $(seq 1 "$MODEM_WAIT_ATTEMPTS"); do
    MODEM_ID=$(mmcli -L 2>/dev/null | grep -oP 'Modem/\K[0-9]+' | head -n1 || true)
    if [ -n "$MODEM_ID" ]; then
        log INFO "Modem detected: ID=$MODEM_ID (attempt $i)"
        break
    fi
    log INFO "Waiting modem detected... ($i/$MODEM_WAIT_ATTEMPTS)"
    sleep 2
done

if [ -z "$MODEM_ID" ]; then
    log FAIL "Modem Not detected after $((MODEM_WAIT_ATTEMPTS*2))s. Check connection USB/serial modem."
    log WARN "Continuing without GSM -- system will depends on WiFi (if exists)."
fi

APN="$DEFAULT_APN"
PROVIDER="Unknown"
REGISTERED=false

if [ -n "$MODEM_ID" ]; then

    if ! mmcli -m "$MODEM_ID" --enable >/dev/null 2>&1; then
        log WARN "mmcli --enable failed or modem already enabled, continue check status."
    fi
    sleep 3

    # -- Check status SIM (locked / missing) so that failure SIM not
    #    ketutup diam-diam like previously.
    SIM_STATUS=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null | grep "modem.generic.state" | cut -d= -f2 | tr -d ' ' || true)
    if [ "$SIM_STATUS" = "locked" ]; then
        log FAIL "Modem inside status 'locked' -- possibly SIM needs PIN. GSM not will can connect until this resolved manual (mmcli -m $MODEM_ID --pin=XXXX)."
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
    # STEP 2: Wait modem ACTUALLY attach to network operator.
    # This section that LOST in version old -- version old only waiting
    # modem "detected", then directly nmcli connection up. Although
    # between "modem detected" and "modem attach to network cellular"
    # (registration-state = home/roaming) can require 10-40 seconds again,
    # terutama if signal weak. If nmcli up dipanggil before this
    # complete, ia gampang timeout -- and version old silences error that
    # with `|| true` so kelihatan "successful" although not.
    # -------------------------------------------------------------------
    for i in $(seq 1 "$REGISTRATION_WAIT_ATTEMPTS"); do
        REG_STATE=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null | grep "modem.3gpp.registration-state" | cut -d= -f2 | tr -d ' ' || true)
        if [ "$REG_STATE" = "home" ] || [ "$REG_STATE" = "roaming" ]; then
            log INFO "Modem registered to network operator (state: $REG_STATE), attempt $i"
            REGISTERED=true
            break
        fi
        log INFO "Waiting registered to network cellular... state when this: ${REG_STATE:-unknown} ($i/$REGISTRATION_WAIT_ATTEMPTS)"
        sleep 2
    done

    if [ "$REGISTERED" = false ]; then
        log FAIL "Modem not successful attach to network operator inside $((REGISTRATION_WAIT_ATTEMPTS*2))s. Signal possible weak or SIM faulty."
    fi
fi

# -----------------------------------------------------------------------
# Configure GSM connection profile (metric low = priority main)
# -----------------------------------------------------------------------
nmcli connection modify "$CONNECTION_NAME" \
    gsm.apn "$APN" \
    connection.autoconnect yes \
    connection.autoconnect-priority 100 \
    ipv4.method auto \
    ipv4.route-metric "$MODEM_METRIC" \
    ipv6.method ignore \
    || log FAIL "Failed memodifikasi profile connection $CONNECTION_NAME"

# -----------------------------------------------------------------------
# Configure WiFi as backup (metric high = priority low, BUT still
# auto-connect so that used if GSM failed total). Section this NOT
# needs WiFi to exist -- if none profile WiFi stored, loop in
# bottom only running above list empty and not perform what-what. Therefore
# absence WiFi NOT prevent steps GSM above or in
# bottom at all.
# -----------------------------------------------------------------------
WIFI_CONNECTIONS=$(nmcli -t -f NAME,TYPE connection show | grep ":802-11-wireless" | cut -d: -f1 || true)

if [ -z "$WIFI_CONNECTIONS" ]; then
    log INFO "None profile WiFi stored -- continue only with GSM."
else
    echo "$WIFI_CONNECTIONS" | while read -r WIFI_NAME; do
        if [ -n "$WIFI_NAME" ]; then
            log INFO "Set WiFi as backup: $WIFI_NAME"
            nmcli connection modify "$WIFI_NAME" \
                connection.autoconnect yes \
                connection.autoconnect-priority 0 \
                ipv4.route-metric "$WIFI_METRIC" \
                ipv6.route-metric "$WIFI_METRIC" \
                || log WARN "Failed memodifikasi profile WiFi $WIFI_NAME"
        fi
    done
fi

# -----------------------------------------------------------------------
# STEP 3: Connect GSM with retry, and VERIFY the result actual --
# not only "nmcli exit 0" but correct-correct check default route through
# interface modem. This also section that lost in version old.
# -----------------------------------------------------------------------
GSM_CONNECTED=false

for attempt in $(seq 1 "$CONNECT_ATTEMPTS"); do
    log INFO "Connecting GSM... attempt $attempt/$CONNECT_ATTEMPTS"

    if nmcli connection up "$CONNECTION_NAME" >/dev/null 2>&1; then
        GSM_IFACE=$(nmcli -g GENERAL.DEVICES connection show "$CONNECTION_NAME" 2>/dev/null | head -n1)
        ROUTE_INFO=$(ip route get 8.8.8.8 2>/dev/null || true)

        if [ -n "$GSM_IFACE" ] && echo "$ROUTE_INFO" | grep -q "dev $GSM_IFACE"; then
            log INFO "GSM connected. Default route terkonfirmasi through interface $GSM_IFACE."
            GSM_CONNECTED=true
            break
        else
            log WARN "nmcli reports success but default route NOT YET through interface GSM ($GSM_IFACE). Possible still held by WiFi metric or not yet got IP."
        fi
    else
        log WARN "nmcli connection up failed on attempt $attempt."
    fi

    if [ "$attempt" -lt "$CONNECT_ATTEMPTS" ]; then
        sleep "$CONNECT_RETRY_DELAY"
    fi
done

if [ "$GSM_CONNECTED" = true ]; then
    log INFO "FINAL STATUS: GSM/SIM successful connect and therefore route main."
else
    log FAIL "FINAL STATUS: GSM/SIM FAILED connect after $CONNECT_ATTEMPTS attempt."
    if [ -n "$WIFI_CONNECTIONS" ]; then
        log WARN "System will rely on WiFi as fallback (if WiFi successful connect)."
    else
        log WARN "None WiFi backup available -- possibly NONE connectivity internet at all. EFWS will run with offline queue."
    fi
fi

log INFO "Current route:"
ip route get 8.8.8.8 2>&1 || log WARN "Cannot resolve route to 8.8.8.8 -- possibly not yet a connection internet at all."

log INFO "Done."

# =============================================================================
# EXIT POLICY (INTENTIONALLY, do not changed without update efws.service also):
# Script this ALWAYS exit 0, although GSM_CONNECTED=false. This konsisten
# with version old, according to dependency `efws.service` that use
# `Requires=gsm-connect.service`. If script this exit non-zero, systemd
# will MEMBLOKIR efws.service at all -- although EFWS has
# offline-queue and still berguna running local although without internet.
# That differs from version old: now status success/failed GSM
# TERCATAT CLEAR in journal, not again dibungkam by `|| true`.
# =============================================================================
exit 0