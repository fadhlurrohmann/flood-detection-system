#!/bin/bash
# =============================================================================
# EWS Communication Check (check_comm.sh)
# =============================================================================
# Purpose: verify end-to-end route komunikasi EFWS -- NOT only check
# whether nmcli/gsm-connect success, but:
#
#   1. Run detect_sim() ORIGINAL from komunikasi/sim_detector.py (code
#      production You its own) for ensuring module A7670E or SIM7600
#      correct-correct readable, its signal level, and already registered to
#      network or not yet.
#   2. Check whether ModemManager & profile GSM already use interface that
#      correct (cdc-wdm, not port serial that used app).
#   3. Check status Tailscale -- whether accept-routes/exit-node active
#      (that can geser default route) and whether DNS in-takeover.
#   4. Tes resolusi DNS + reachability actual to EFWS_API_URL, simultaneously
#      show through interface which traffic that correct-correct exit.
#
# IMPORTANT: Run script this WHEN efws.service IS STOPPED.
# Why: sim_detector.py opens /dev/ttyUSB* in a eksklusif via
# pyserial. If efws.service still running and already holding port that,
# script this will failed open port that same (port busy) -- that NOT
# means the modem faulty, only because two process compete for port that same.
#
# Usage:
#   sudo systemctl stop efws
#   /home/uwfadmin/ews/scripts/check_comm.sh
#   sudo systemctl start efws
# =============================================================================

set -u

PROJECT_DIR="/home/uwfadmin/ews"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python3"
CONNECTION_NAME="EWS-4G"

pass=0; warn=0; fail=0

log()  { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
ok()   { printf '  \033[1;32m[OK]\033[0m   %s\n' "$*";   pass=$((pass+1)); }
w()    { printf '  \033[1;33m[WARN]\033[0m %s\n' "$*";   warn=$((warn+1)); }
f()    { printf '  \033[1;31m[FAIL]\033[0m %s\n' "$*";   fail=$((fail+1)); }
info() { printf '  %s\n' "$*"; }

# =============================================================================
# 0. Guard: make sure efws.service not medium holding port serial
# =============================================================================
log "0. Check status efws.service"
if systemctl is-active --quiet efws; then
    w "efws.service MEDIUM RUNNING. This can bikin sim_detector.py below failed open port (busy)."
    info "Recommended: sudo systemctl stop efws   (then start again after complete diagnostics)"
else
    ok "efws.service not medium running -- safe for tes port serial."
fi

# =============================================================================
# 1. ModemManager: modem detected? primary port what?
# =============================================================================
log "1. ModemManager & primary port modem"

MODEM_ID=$(mmcli -L 2>/dev/null | grep -oP 'Modem/\K[0-9]+' | head -n1 || true)
if [ -z "$MODEM_ID" ]; then
    f "mmcli not find modem at all. Check 'lsusb' and 'ls /dev/ttyUSB*'."
else
    ok "Modem detected ModemManager, ID=$MODEM_ID"
    MM_INFO=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null)

    PRIMARY_PORT=$(echo "$MM_INFO" | grep -oP 'modem\.generic\.primary-port\s*:\s*\K.*' | tr -d '[:space:]' || true)
    MODEL=$(echo "$MM_INFO" | grep -oP 'modem\.generic\.model\s*:\s*\K.*' || true)
    STATE=$(echo "$MM_INFO" | grep -oP 'modem\.generic\.state\s*:\s*\K.*' | tr -d '[:space:]' || true)

    info "Model         : ${MODEL:-unknown}"
    info "Primary port  : ${PRIMARY_PORT:-unknown}"
    info "Modem state   : ${STATE:-unknown}"

    case "$PRIMARY_PORT" in
        cdc-wdm*) ok "Primary port use cdc-wdm (QMI) -- separate from port serial AT, safe from bentrok with app." ;;
        "")       w "Cannot read primary-port from mmcli." ;;
        *)        f "Primary port ($PRIMARY_PORT) NOT cdc-wdm. Possibly modem mode PPP/AT -- risk compete for port with sim_detector.py HIGH." ;;
    esac

    if [ "$STATE" = "locked" ]; then
        f "Modem berstatus 'locked' -- SIM possibly needs PIN."
    fi

    # Profile connection GSM: check ifname that actually used
    CONN_IFACE=$(nmcli -g connection.interface-name connection show "$CONNECTION_NAME" 2>/dev/null || true)
    if [ -n "$CONN_IFACE" ]; then
        info "Profile '$CONNECTION_NAME' use interface-name: ${CONN_IFACE:-<auto/any>}"
        if [ -n "$PRIMARY_PORT" ] && [ "$CONN_IFACE" != "$PRIMARY_PORT" ] && [ "$CONN_IFACE" != "*" ] && [ -n "$CONN_IFACE" ]; then
            w "Interface profile ($CONN_IFACE) differs from with primary-port modem ($PRIMARY_PORT) -- check configuration gsm_connect.sh."
        fi
    fi
fi

# =============================================================================
# 2. Run detect_sim() ORIGINAL from code aplikasi -- this correct-correct
#    run "section communication"-nya, not simulasi.
# =============================================================================
log "2. Run communication/sim_detector.py (detect_sim, force_scan)"

if [ ! -x "$VENV_PYTHON" ]; then
    f "Not find venv python in $VENV_PYTHON -- adjust PROJECT_DIR above script this."
else
    cd "$PROJECT_DIR" || exit 1
    DETECT_OUTPUT=$("$VENV_PYTHON" - <<'PYEOF' 2>&1
import sys, json
sys.path.insert(0, ".")
try:
    from communication.sim_detector import detect_sim
    from config import settings
    if settings.RUN_MODE == "mock":
        print("RESULT::MOCK_MODE")
        sys.exit(0)
    sim = detect_sim(force_scan=True)
    reg = sim.network_registration()
    csq = sim.signal_quality()
    print(f"RESULT::OK::module={sim.module}::port={sim.port}")
    print(f"REGISTRATION::{reg.strip()}")
    print(f"SIGNAL::{csq.strip()}")
    sim.close()
except Exception as e:
    print(f"RESULT::ERROR::{type(e).__name__}: {e}")
    sys.exit(1)
PYEOF
)
    RC=$?
    echo "$DETECT_OUTPUT" | sed 's/^/  /'

    if echo "$DETECT_OUTPUT" | grep -q "RESULT::MOCK_MODE"; then
        w "EFWS_RUN_MODE=mock in .env -- sim_detector not dites to hardware original. Set EFWS_RUN_MODE=hardware for tes this."
    elif echo "$DETECT_OUTPUT" | grep -q "RESULT::OK"; then
        ok "detect_sim() successful -- module and port readable."
        if echo "$DETECT_OUTPUT" | grep -qi "REGISTRATION::.*+CREG: [0-9],1\|REGISTRATION::.*+CREG: [0-9],5"; then
            ok "Modem already registered to network (home/roaming)."
        else
            w "Status registered not shows home/roaming -- check signal/APN/SIM."
        fi
    else
        f "detect_sim() failed. See error message above (possibly port busy if efws.service still running, or modem memang not detected)."
    fi
fi

# =============================================================================
# 3. Tailscale: make sure not menggeser default route, check status DNS
# =============================================================================
log "3. Tailscale"

if ! command -v tailscale >/dev/null 2>&1; then
    info "Tailscale is not installed in system this -- skip the check."
else
    if ! systemctl is-active --quiet tailscaled; then
        w "tailscaled terinstall but not active."
    else
        ok "tailscaled active."
        TS_STATUS=$(tailscale status --json 2>/dev/null || true)

        if echo "$TS_STATUS" | grep -q '"ExitNodeStatus"'; then
            EXIT_NODE=$(echo "$TS_STATUS" | grep -oP '"ExitNodeStatus"\s*:\s*\K[^,}]*' || true)
        fi

        # Check prefs: AcceptRoutes / ExitNodeID through 'tailscale debug prefs' if available
        TS_PREFS=$(tailscale debug prefs 2>/dev/null || true)
        if echo "$TS_PREFS" | grep -qi '"RouteAll": *true\|"AcceptRoutes": *true'; then
            w "Tailscale AcceptRoutes active -- if one tailnet peer advertise 0.0.0.0/0 (exit node), this CAN menggeser default route menjauh from GSM/WiFi. Make sure this memang disengaja."
        else
            ok "AcceptRoutes not terindikasi active -- default route GSM/WiFi not terganggu Tailscale."
        fi

        if echo "$TS_PREFS" | grep -qi '"ExitNodeID": *""' || ! echo "$TS_PREFS" | grep -qi '"ExitNodeID"'; then
            ok "Not medium using exit node -- default route safe."
        else
            w "Appears medium using Tailscale exit node -- ALL traffic (including to EFWS_API_URL) will through tailnet, not through GSM directly."
        fi

        # DNS takeover check
        if command -v resolvectl >/dev/null 2>&1; then
            RESOLV_INFO=$(resolvectl status 2>/dev/null || true)
            if echo "$RESOLV_INFO" | grep -q "100.100.100.100"; then
                info "Tailscale MagicDNS (100.100.100.100) active as one DNS server."
                w "If resolusi hostname EFWS_API_URL tiba-tiba slow/failed although connection GSM sehat, try: sudo tailscale set --accept-dns=false then tes again."
            else
                ok "Tailscale not retrieving alih DNS resolver global."
            fi
        fi
    fi
fi

# =============================================================================
# 4. Default route + DNS + reachability actual to EFWS_API_URL
# =============================================================================
log "4. Default route, DNS, and reachability to EFWS_API_URL"

ROUTE_INFO=$(ip route get 8.8.8.8 2>&1 || true)
info "$ROUTE_INFO"
ACTIVE_IFACE=$(echo "$ROUTE_INFO" | grep -oP 'dev \K[^ ]+' | head -n1 || true)
info "Interface active for internet when this: ${ACTIVE_IFACE:-not diketahui}"

if [ "$ACTIVE_IFACE" = "cdc-wdm0" ] || echo "$ACTIVE_IFACE" | grep -q "wwan\|cdc-wdm"; then
    ok "Default route through modem GSM (according to priority that desired)."
elif [ -n "$ACTIVE_IFACE" ]; then
    w "Default route when this through '$ACTIVE_IFACE' (not GSM). If GSM medium connected also, check again route-metric-nya."
fi

# Get EFWS_API_URL from .env project for tes directly
API_URL=$(grep -m1 '^EFWS_API_URL=' "$PROJECT_DIR/.env" 2>/dev/null | cut -d= -f2- | sed -e 's/\r$//' -e "s/^['\"]//" -e "s/['\"]$//")
if [ -z "$API_URL" ]; then
    w "Not find EFWS_API_URL in $PROJECT_DIR/.env -- lewati tes reachability endpoint."
else
    API_HOST=$(echo "$API_URL" | sed -E 's#^[a-zA-Z]+://##; s#[/:].*$##')
    info "Endpoint from .env : $API_URL"
    info "Host that in-resolve: $API_HOST"

    if command -v getent >/dev/null 2>&1; then
        DNS_RESULT=$(getent hosts "$API_HOST" 2>&1 || true)
        if [ -n "$DNS_RESULT" ]; then
            ok "DNS resolve success: $DNS_RESULT"
        else
            f "DNS resolve FAILED for $API_HOST. Check resolver active (resolvectl status) or APN operator."
        fi
    fi

    if command -v curl >/dev/null 2>&1; then
        HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API_URL" 2>&1 || true)
        if [ -n "$HTTP_CODE" ] && [ "$HTTP_CODE" != "000" ]; then
            ok "Endpoint got dihubungi (HTTP $HTTP_CODE) through interface $ACTIVE_IFACE."
        else
            f "Failed reach $API_URL (curl exit/HTTP: $HTTP_CODE). Check connection & firewall APN."
        fi
    fi
fi

# =============================================================================
# Ringkasan
# =============================================================================
log "Ringkasan"
info "OK=$pass  WARN=$warn  FAIL=$fail"
if [ "$fail" -gt 0 ]; then
    info "Exists failure that needs ditindaklanjuti before sure route komunikasi sehat."
elif [ "$warn" -gt 0 ]; then
    info "None failure fatal, but several items for checked manual (see WARN above)."
else
    info "All checks passed."
fi
