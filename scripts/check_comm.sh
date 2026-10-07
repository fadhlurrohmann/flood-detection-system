#!/bin/bash
# =============================================================================
# EWS Communication Check (check_comm.sh)
# =============================================================================
# Purpose: verify the EFWS communication path end-to-end -- NOT just whether
# nmcli/gsm-connect succeeded, but:
#
#   1. Run the REAL detect_sim() from communication/sim_detector.py (your own
#      production code) to make sure the A7670E or SIM7600 module is
#      actually read, what its signal is, and whether it has registered
#      on the network yet.
#   2. Check whether ModemManager & the GSM profile use the right
#      interface (cdc-wdm, not the serial port the app uses).
#   3. Check the Tailscale status -- whether accept-routes/exit-node is active
#      (which can shift the default route) and whether DNS is taken over.
#   4. Test DNS resolution + real reachability to EFWS_API_URL, and at the
#      same time show which interface that traffic actually leaves through.
#
# IMPORTANT: Run this script WHILE efws.service is STOPPED.
# Why: sim_detector.py opens /dev/ttyUSB* exclusively via
# pyserial. If efws.service is still running and already holds that port,
# this script will fail to open the same port (port busy) -- that does NOT
# mean the modem is broken, only that two processes are fighting over the same port.
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
# 0. Guard: make sure efws.service is not holding the serial port
# =============================================================================
log "0. Check the efws.service status"
if systemctl is-active --quiet efws; then
    w "efws.service is RUNNING. This can make sim_detector.py below fail to open the port (busy)."
    info "Recommended: sudo systemctl stop efws   (then start it again after the diagnostics)"
else
    ok "efws.service is not running -- safe to test the serial port."
fi

# =============================================================================
# 1. ModemManager: is the modem detected? What is the primary port?
# =============================================================================
log "1. ModemManager & the modem's primary port"

MODEM_ID=$(mmcli -L 2>/dev/null | grep -oP 'Modem/\K[0-9]+' | head -n1 || true)
if [ -z "$MODEM_ID" ]; then
    f "mmcli found no modem at all. Check 'lsusb' and 'ls /dev/ttyUSB*'."
else
    ok "Modem detected by ModemManager, ID=$MODEM_ID"
    MM_INFO=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null)

    PRIMARY_PORT=$(echo "$MM_INFO" | grep -oP 'modem\.generic\.primary-port\s*:\s*\K.*' | tr -d '[:space:]' || true)
    MODEL=$(echo "$MM_INFO" | grep -oP 'modem\.generic\.model\s*:\s*\K.*' || true)
    STATE=$(echo "$MM_INFO" | grep -oP 'modem\.generic\.state\s*:\s*\K.*' | tr -d '[:space:]' || true)

    info "Model         : ${MODEL:-unknown}"
    info "Primary port  : ${PRIMARY_PORT:-unknown}"
    info "Modem state   : ${STATE:-unknown}"

    case "$PRIMARY_PORT" in
        cdc-wdm*) ok "The primary port uses cdc-wdm (QMI) -- separate from the AT serial port, safe from conflicts with the app." ;;
        "")       w "Could not read the primary-port from mmcli." ;;
        *)        f "The primary port ($PRIMARY_PORT) is NOT cdc-wdm. The modem is probably in PPP/AT mode -- the risk of a port fight with sim_detector.py is HIGH." ;;
    esac

    if [ "$STATE" = "locked" ]; then
        f "The modem's state is 'locked' -- the SIM probably needs a PIN."
    fi

    # GSM connection profile: check the ifname that is actually used
    CONN_IFACE=$(nmcli -g connection.interface-name connection show "$CONNECTION_NAME" 2>/dev/null || true)
    if [ -n "$CONN_IFACE" ]; then
        info "Profile '$CONNECTION_NAME' uses interface-name: ${CONN_IFACE:-<auto/any>}"
        if [ -n "$PRIMARY_PORT" ] && [ "$CONN_IFACE" != "$PRIMARY_PORT" ] && [ "$CONN_IFACE" != "*" ] && [ -n "$CONN_IFACE" ]; then
            w "The profile interface ($CONN_IFACE) differs from the modem primary-port ($PRIMARY_PORT) -- check the gsm_connect.sh configuration."
        fi
    fi
fi

# =============================================================================
# 2. Run the REAL detect_sim() from the application code -- this really
#    runs the "communication part", not a simulation.
# =============================================================================
log "2. Run communication/sim_detector.py (detect_sim, force_scan)"

if [ ! -x "$VENV_PYTHON" ]; then
    f "Could not find the venv python at $VENV_PYTHON -- adjust PROJECT_DIR at the top of this script."
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
        w "EFWS_RUN_MODE=mock in .env -- sim_detector is not tested against real hardware. Set EFWS_RUN_MODE=hardware for this test."
    elif echo "$DETECT_OUTPUT" | grep -q "RESULT::OK"; then
        ok "detect_sim() succeeded -- the module and port were read."
        if echo "$DETECT_OUTPUT" | grep -qi "REGISTRATION::.*+CREG: [0-9],1\|REGISTRATION::.*+CREG: [0-9],5"; then
            ok "The modem has registered on the network (home/roaming)."
        else
            w "The registration status does not show home/roaming -- check the signal/APN/SIM."
        fi
    else
        f "detect_sim() failed. See the error message above (probably port busy if efws.service is still running, or the modem is really not detected)."
    fi
fi

# =============================================================================
# 3. Tailscale: make sure it does not shift the default route, check the DNS status
# =============================================================================
log "3. Tailscale"

if ! command -v tailscale >/dev/null 2>&1; then
    info "Tailscale is not installed on this system -- skipping the check."
else
    if ! systemctl is-active --quiet tailscaled; then
        w "tailscaled is installed but not active."
    else
        ok "tailscaled is active."
        TS_STATUS=$(tailscale status --json 2>/dev/null || true)

        if echo "$TS_STATUS" | grep -q '"ExitNodeStatus"'; then
            EXIT_NODE=$(echo "$TS_STATUS" | grep -oP '"ExitNodeStatus"\s*:\s*\K[^,}]*' || true)
        fi

        # Check prefs: AcceptRoutes / ExitNodeID via 'tailscale debug prefs' if available
        TS_PREFS=$(tailscale debug prefs 2>/dev/null || true)
        if echo "$TS_PREFS" | grep -qi '"RouteAll": *true\|"AcceptRoutes": *true'; then
            w "Tailscale AcceptRoutes is active -- if one of the tailnet peers advertises 0.0.0.0/0 (exit node), this CAN shift the default route away from GSM/WiFi. Make sure this is intended."
        else
            ok "AcceptRoutes is not indicated as active -- the GSM/WiFi default route is not disturbed by Tailscale."
        fi

        if echo "$TS_PREFS" | grep -qi '"ExitNodeID": *""' || ! echo "$TS_PREFS" | grep -qi '"ExitNodeID"'; then
            ok "Not using an exit node -- the default route is safe."
        else
            w "It looks like a Tailscale exit node is in use -- ALL traffic (including to EFWS_API_URL) will go through the tailnet, not directly through GSM."
        fi

        # DNS takeover check
        if command -v resolvectl >/dev/null 2>&1; then
            RESOLV_INFO=$(resolvectl status 2>/dev/null || true)
            if echo "$RESOLV_INFO" | grep -q "100.100.100.100"; then
                info "Tailscale MagicDNS (100.100.100.100) is active as one of the DNS servers."
                w "If resolving the EFWS_API_URL hostname suddenly becomes slow/fails even though the GSM connection is healthy, try: sudo tailscale set --accept-dns=false and test again."
            else
                ok "Tailscale is not taking over the global DNS resolver."
            fi
        fi
    fi
fi

# =============================================================================
# 4. Default route + DNS + real reachability to EFWS_API_URL
# =============================================================================
log "4. Default route, DNS, and reachability to EFWS_API_URL"

ROUTE_INFO=$(ip route get 8.8.8.8 2>&1 || true)
info "$ROUTE_INFO"
ACTIVE_IFACE=$(echo "$ROUTE_INFO" | grep -oP 'dev \K[^ ]+' | head -n1 || true)
info "Interface currently active for the internet: ${ACTIVE_IFACE:-unknown}"

if [ "$ACTIVE_IFACE" = "cdc-wdm0" ] || echo "$ACTIVE_IFACE" | grep -q "wwan\|cdc-wdm"; then
    ok "The default route goes through the GSM modem (per the desired priority)."
elif [ -n "$ACTIVE_IFACE" ]; then
    w "The default route currently goes through '$ACTIVE_IFACE' (not GSM). If GSM is also connected, re-check its route-metric."
fi

# Get EFWS_API_URL from the project .env for a direct test
API_URL=$(grep -m1 '^EFWS_API_URL=' "$PROJECT_DIR/.env" 2>/dev/null | cut -d= -f2- | sed -e 's/\r$//' -e "s/^['\"]//" -e "s/['\"]$//")
if [ -z "$API_URL" ]; then
    w "Could not find EFWS_API_URL in $PROJECT_DIR/.env -- skipping the endpoint reachability test."
else
    API_HOST=$(echo "$API_URL" | sed -E 's#^[a-zA-Z]+://##; s#[/:].*$##')
    info "Endpoint from .env : $API_URL"
    info "Host being resolved: $API_HOST"

    if command -v getent >/dev/null 2>&1; then
        DNS_RESULT=$(getent hosts "$API_HOST" 2>&1 || true)
        if [ -n "$DNS_RESULT" ]; then
            ok "DNS resolve succeeded: $DNS_RESULT"
        else
            f "DNS resolve FAILED for $API_HOST. Check the active resolver (resolvectl status) or the operator APN."
        fi
    fi

    if command -v curl >/dev/null 2>&1; then
        HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API_URL" 2>&1 || true)
        if [ -n "$HTTP_CODE" ] && [ "$HTTP_CODE" != "000" ]; then
            ok "The endpoint can be reached (HTTP $HTTP_CODE) through interface $ACTIVE_IFACE."
        else
            f "Failed to reach $API_URL (curl exit/HTTP: $HTTP_CODE). Check the connection & the APN firewall."
        fi
    fi
fi

# =============================================================================
# Summary
# =============================================================================
log "Summary"
info "OK=$pass  WARN=$warn  FAIL=$fail"
if [ "$fail" -gt 0 ]; then
    info "There are failures to follow up on before you can be sure the communication path is healthy."
elif [ "$warn" -gt 0 ]; then
    info "No fatal failures, but there are a few things to check manually (see the WARN lines above)."
else
    info "All checks passed."
fi
