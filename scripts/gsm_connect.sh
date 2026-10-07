#!/bin/bash
# =============================================================================
# EWS GSM Auto Connect (v2)
# =============================================================================
# Main changes from the previous version:
#   1. Waits for the modem to be TRULY registered on the operator network (3GPP
#      attach), not just for the modem to be detected by ModemManager.
#   2. `nmcli connection up` is tried several times (retry+backoff), and
#      each attempt is verified by checking that the default route really goes
#      through the modem interface -- not just an exit 0.
#   3. All critical steps are logged with a clear status (OK/WARN/FAIL)
#      and a timestamp, no more `|| true` silencing failures.
#   4. The SIM status (locked/PIN) is also checked so that if the SIM gets locked, it
#      shows up in the log right away instead of silently failing to connect.
#   5. The script's exit code STILL always ends at 0 (see the "EXIT POLICY" section
#      below) -- this is DELIBERATELY kept the same as the old version,
#      so efws.service (which uses Requires=gsm-connect.service)
#      still starts even if GSM fails completely, and EFWS can run using the
#      offline queue / WiFi backup. What changed is not the exit code,
#      but WHETHER GSM actually connected or not is now clearly
#      recorded in the journal (journalctl -u gsm-connect).
# =============================================================================

set -u

CONNECTION_NAME="EWS-4G"
DEFAULT_APN="internet"
MODEM_METRIC=50
WIFI_METRIC=600

MODEM_WAIT_ATTEMPTS=30       # wait for the modem to be detected: 30 x 2s = 60s
REGISTRATION_WAIT_ATTEMPTS=30 # wait to attach to the network: 30 x 2s = 60s
CONNECT_ATTEMPTS=4            # nmcli connection up attempts
CONNECT_RETRY_DELAY=5         # pause between attempts (seconds)

# -----------------------------------------------------------------------
# Logging helper -- every log has a timestamp + level, and goes to journald
# through StandardOutput=journal in the service file, so it can be viewed with:
#   journalctl -u gsm-connect -b
# -----------------------------------------------------------------------
log() {
    local level="$1"; shift
    printf '[EWS-GSM][%s] %s: %s\n' "$(date '+%H:%M:%S')" "$level" "$*"
}

log INFO "Starting GSM auto connect..."

systemctl is-active --quiet ModemManager || systemctl start ModemManager
systemctl is-active --quiet NetworkManager || systemctl start NetworkManager

nmcli radio wwan on || log WARN "Failed to enable the wwan radio (maybe it is already on)"

# Create GSM connection profile if not exists
if ! nmcli connection show "$CONNECTION_NAME" >/dev/null 2>&1; then
    log INFO "Creating a new GSM profile: $CONNECTION_NAME"
    if ! nmcli connection add type gsm ifname "*" con-name "$CONNECTION_NAME" apn "$DEFAULT_APN"; then
        log FAIL "Failed to create the GSM profile. Check whether the NetworkManager-gsm plugin is installed."
    fi
fi

# -----------------------------------------------------------------------
# STEP 1: Wait for the modem to be detected by ModemManager
# -----------------------------------------------------------------------
MODEM_ID=""
for i in $(seq 1 "$MODEM_WAIT_ATTEMPTS"); do
    MODEM_ID=$(mmcli -L 2>/dev/null | grep -oP 'Modem/\K[0-9]+' | head -n1 || true)
    if [ -n "$MODEM_ID" ]; then
        log INFO "Modem detected: ID=$MODEM_ID (attempt $i)"
        break
    fi
    log INFO "Waiting for the modem to be detected... ($i/$MODEM_WAIT_ATTEMPTS)"
    sleep 2
done

if [ -z "$MODEM_ID" ]; then
    log FAIL "Modem NOT detected after $((MODEM_WAIT_ATTEMPTS*2))s. Check the modem's USB/serial connection."
    log WARN "Continuing without GSM -- the system will depend on WiFi (if any)."
fi

APN="$DEFAULT_APN"
PROVIDER="Unknown"
REGISTERED=false

if [ -n "$MODEM_ID" ]; then

    if ! mmcli -m "$MODEM_ID" --enable >/dev/null 2>&1; then
        log WARN "mmcli --enable failed or the modem is already enabled, continuing to check the status."
    fi
    sleep 3

    # -- Check the SIM status (locked / missing) so that a SIM failure is not
    #    silently covered up like before.
    SIM_STATUS=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null | grep "modem.generic.state" | cut -d= -f2 | tr -d ' ' || true)
    if [ "$SIM_STATUS" = "locked" ]; then
        log FAIL "The modem is in the 'locked' state -- the SIM probably needs a PIN. GSM will not be able to connect until this is sorted out manually (mmcli -m $MODEM_ID --pin=XXXX)."
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
    log INFO "APN in use        : $APN"

    # -------------------------------------------------------------------
    # STEP 2: Wait for the modem to be TRULY attached to the operator network.
    # This is the part that was MISSING in the old version -- the old version only waited
    # for the modem to be "detected", then went straight to nmcli connection up. Yet
    # between "modem detected" and "modem attached to the cellular network"
    # (registration-state = home/roaming) it can take another 10-40 seconds,
    # especially if the signal is weak. If nmcli up is called before this
    # finishes, it easily times out -- and the old version silenced that error
    # with `|| true` so it looked "successful" when it was not.
    # -------------------------------------------------------------------
    for i in $(seq 1 "$REGISTRATION_WAIT_ATTEMPTS"); do
        REG_STATE=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null | grep "modem.3gpp.registration-state" | cut -d= -f2 | tr -d ' ' || true)
        if [ "$REG_STATE" = "home" ] || [ "$REG_STATE" = "roaming" ]; then
            log INFO "Modem registered on the operator network (state: $REG_STATE), attempt $i"
            REGISTERED=true
            break
        fi
        log INFO "Waiting for registration on the cellular network... current state: ${REG_STATE:-unknown} ($i/$REGISTRATION_WAIT_ATTEMPTS)"
        sleep 2
    done

    if [ "$REGISTERED" = false ]; then
        log FAIL "The modem did not manage to attach to the operator network within $((REGISTRATION_WAIT_ATTEMPTS*2))s. The signal may be weak or the SIM has a problem."
    fi
fi

# -----------------------------------------------------------------------
# Configure GSM connection profile (low metric = top priority)
# -----------------------------------------------------------------------
nmcli connection modify "$CONNECTION_NAME" \
    gsm.apn "$APN" \
    connection.autoconnect yes \
    connection.autoconnect-priority 100 \
    ipv4.method auto \
    ipv4.route-metric "$MODEM_METRIC" \
    ipv6.method ignore \
    || log FAIL "Failed to modify the connection profile $CONNECTION_NAME"

# -----------------------------------------------------------------------
# Configure WiFi as backup (high metric = low priority, BUT still
# auto-connect so it is used if GSM fails completely). This part does NOT
# need WiFi to exist -- if there is no saved WiFi profile, the loop
# below just runs over an empty list and does nothing. So the
# absence of WiFi does NOT block the GSM steps above or
# below at all.
# -----------------------------------------------------------------------
WIFI_CONNECTIONS=$(nmcli -t -f NAME,TYPE connection show | grep ":802-11-wireless" | cut -d: -f1 || true)

if [ -z "$WIFI_CONNECTIONS" ]; then
    log INFO "No saved WiFi profile -- continuing with GSM only."
else
    echo "$WIFI_CONNECTIONS" | while read -r WIFI_NAME; do
        if [ -n "$WIFI_NAME" ]; then
            log INFO "Set WiFi as backup: $WIFI_NAME"
            nmcli connection modify "$WIFI_NAME" \
                connection.autoconnect yes \
                connection.autoconnect-priority 0 \
                ipv4.route-metric "$WIFI_METRIC" \
                ipv6.route-metric "$WIFI_METRIC" \
                || log WARN "Failed to modify the WiFi profile $WIFI_NAME"
        fi
    done
fi

# -----------------------------------------------------------------------
# STEP 3: Connect GSM with retry, and VERIFY the real result --
# not just "nmcli exit 0" but actually check that the default route goes through the
# modem interface. This is also a part that was missing in the old version.
# -----------------------------------------------------------------------
GSM_CONNECTED=false

for attempt in $(seq 1 "$CONNECT_ATTEMPTS"); do
    log INFO "Connecting GSM... attempt $attempt/$CONNECT_ATTEMPTS"

    if nmcli connection up "$CONNECTION_NAME" >/dev/null 2>&1; then
        GSM_IFACE=$(nmcli -g GENERAL.DEVICES connection show "$CONNECTION_NAME" 2>/dev/null | head -n1)
        ROUTE_INFO=$(ip route get 8.8.8.8 2>/dev/null || true)

        if [ -n "$GSM_IFACE" ] && echo "$ROUTE_INFO" | grep -q "dev $GSM_IFACE"; then
            log INFO "GSM connected. Default route confirmed through interface $GSM_IFACE."
            GSM_CONNECTED=true
            break
        else
            log WARN "nmcli reported success but the default route does NOT go through the GSM interface yet ($GSM_IFACE). It may still be held back by the WiFi metric or have no IP yet."
        fi
    else
        log WARN "nmcli connection up failed on attempt $attempt."
    fi

    if [ "$attempt" -lt "$CONNECT_ATTEMPTS" ]; then
        sleep "$CONNECT_RETRY_DELAY"
    fi
done

if [ "$GSM_CONNECTED" = true ]; then
    log INFO "FINAL STATUS: GSM/SIM connected successfully and is the primary path."
else
    log FAIL "FINAL STATUS: GSM/SIM FAILED to connect after $CONNECT_ATTEMPTS attempts."
    if [ -n "$WIFI_CONNECTIONS" ]; then
        log WARN "The system will rely on WiFi as a fallback (if WiFi manages to connect)."
    else
        log WARN "No WiFi backup available -- there is probably NO internet connectivity at all. EFWS will run with the offline queue."
    fi
fi

log INFO "Current route:"
ip route get 8.8.8.8 2>&1 || log WARN "Cannot resolve the route to 8.8.8.8 -- there is probably no internet connection at all yet."

log INFO "Done."

# =============================================================================
# EXIT POLICY (DELIBERATE, do not change it without updating efws.service too):
# This script ALWAYS exits 0, even if GSM_CONNECTED=false. This is consistent
# with the old version, per the `efws.service` dependency which uses
# `Requires=gsm-connect.service`. If this script exits non-zero, systemd
# will BLOCK efws.service entirely -- even though EFWS has an
# offline queue and is still useful running locally without internet.
# What differs from the old version: the GSM success/failure status is now
# CLEARLY RECORDED in the journal, no longer silenced by `|| true`.
# =============================================================================
exit 0
