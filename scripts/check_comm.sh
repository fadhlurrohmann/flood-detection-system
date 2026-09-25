#!/bin/bash
# =============================================================================
# EWS Communication Check (check_comm.sh)
# =============================================================================
# Tujuan: verifikasi end-to-end jalur komunikasi EFWS -- NOT only check
# apakah nmcli/gsm-connect sukses, tapi:
#
#   1. Run detect_sim() ASLI from komunikasi/sim_detector.py (kode
#      produksi Anda sendiri) for memastikan module A7670E or SIM7600
#      correct-correct readable, sinyalnya berapa, dan sudah registrasi ke
#      jaringan or belum.
#   2. Check apakah ModemManager & profil GSM sudah use interface that
#      correct (cdc-wdm, not port serial that used app).
#   3. Check status Tailscale -- apakah accept-routes/exit-node aktif
#      (that bisa geser default route) dan apakah DNS di-takeover.
#   4. Tes resolusi DNS + reachability real ke EFWS_API_URL, sekaligus
#      tunjukkan through interface mana traffic itu correct-correct exit.
#
# PENTING: Run skrip ini WHEN efws.service SEDANG BERHENTI.
# Kenapa: sim_detector.py membuka /dev/ttyUSB* secara eksklusif via
# pyserial. If efws.service masih jalan dan sudah pegang port itu,
# skrip ini akan failed buka port that sama (port busy) -- itu NOT
# berarti modemnya rusak, only because dua proses rebutan port that sama.
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
# 0. Guard: make sure efws.service not sedang pegang port serial
# =============================================================================
log "0. Check status efws.service"
if systemctl is-active --quiet efws; then
    w "efws.service SEDANG JALAN. Ini bisa bikin sim_detector.py di bawah failed buka port (busy)."
    info "Disarankan: sudo systemctl stop efws   (lalu start lagi after complete diagnostik)"
else
    ok "efws.service not sedang running -- safe for tes port serial."
fi

# =============================================================================
# 1. ModemManager: modem detected? primary port apa?
# =============================================================================
log "1. ModemManager & primary port modem"

MODEM_ID=$(mmcli -L 2>/dev/null | grep -oP 'Modem/\K[0-9]+' | head -n1 || true)
if [ -z "$MODEM_ID" ]; then
    f "mmcli not menemukan modem sama sekali. Check 'lsusb' dan 'ls /dev/ttyUSB*'."
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
        *)        f "Primary port ($PRIMARY_PORT) NOT cdc-wdm. Possibly modem mode PPP/AT -- risiko rebutan port with sim_detector.py HIGH." ;;
    esac

    if [ "$STATE" = "locked" ]; then
        f "Modem berstatus 'locked' -- SIM possibly needs PIN."
    fi

    # Profil connection GSM: check ifname that sebenarnya used
    CONN_IFACE=$(nmcli -g connection.interface-name connection show "$CONNECTION_NAME" 2>/dev/null || true)
    if [ -n "$CONN_IFACE" ]; then
        info "Profil '$CONNECTION_NAME' use interface-name: ${CONN_IFACE:-<auto/any>}"
        if [ -n "$PRIMARY_PORT" ] && [ "$CONN_IFACE" != "$PRIMARY_PORT" ] && [ "$CONN_IFACE" != "*" ] && [ -n "$CONN_IFACE" ]; then
            w "Interface profil ($CONN_IFACE) beda with primary-port modem ($PRIMARY_PORT) -- check configuration gsm_connect.sh."
        fi
    fi
fi

# =============================================================================
# 2. Run detect_sim() ASLI from kode aplikasi -- ini correct-correct
#    menjalankan "section communication"-nya, not simulasi.
# =============================================================================
log "2. Run communication/sim_detector.py (detect_sim, force_scan)"

if [ ! -x "$VENV_PYTHON" ]; then
    f "Not menemukan venv python di $VENV_PYTHON -- sesuaikan PROJECT_DIR di atas skrip ini."
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
        w "EFWS_RUN_MODE=mock di .env -- sim_detector not dites ke hardware original. Set EFWS_RUN_MODE=hardware for tes ini."
    elif echo "$DETECT_OUTPUT" | grep -q "RESULT::OK"; then
        ok "detect_sim() successful -- module dan port readable."
        if echo "$DETECT_OUTPUT" | grep -qi "REGISTRATION::.*+CREG: [0-9],1\|REGISTRATION::.*+CREG: [0-9],5"; then
            ok "Modem sudah registrasi ke jaringan (home/roaming)."
        else
            w "Status registrasi not menunjukkan home/roaming -- check signal/APN/SIM."
        fi
    else
        f "detect_sim() failed. See error message di atas (possibly port busy if efws.service masih jalan, or modem memang not detected)."
    fi
fi

# =============================================================================
# 3. Tailscale: make sure not menggeser default route, check status DNS
# =============================================================================
log "3. Tailscale"

if ! command -v tailscale >/dev/null 2>&1; then
    info "Tailscale is not installed di sistem ini -- lewati pengecekan."
else
    if ! systemctl is-active --quiet tailscaled; then
        w "tailscaled terinstall tapi not aktif."
    else
        ok "tailscaled aktif."
        TS_STATUS=$(tailscale status --json 2>/dev/null || true)

        if echo "$TS_STATUS" | grep -q '"ExitNodeStatus"'; then
            EXIT_NODE=$(echo "$TS_STATUS" | grep -oP '"ExitNodeStatus"\s*:\s*\K[^,}]*' || true)
        fi

        # Check prefs: AcceptRoutes / ExitNodeID through 'tailscale debug prefs' if available
        TS_PREFS=$(tailscale debug prefs 2>/dev/null || true)
        if echo "$TS_PREFS" | grep -qi '"RouteAll": *true\|"AcceptRoutes": *true'; then
            w "Tailscale AcceptRoutes aktif -- if wrong satu tailnet peer advertise 0.0.0.0/0 (exit node), ini BISA menggeser default route menjauh from GSM/WiFi. Make sure ini memang disengaja."
        else
            ok "AcceptRoutes not terindikasi aktif -- default route GSM/WiFi not terganggu Tailscale."
        fi

        if echo "$TS_PREFS" | grep -qi '"ExitNodeID": *""' || ! echo "$TS_PREFS" | grep -qi '"ExitNodeID"'; then
            ok "Not sedang memakai exit node -- default route safe."
        else
            w "Tampaknya sedang memakai Tailscale exit node -- ALL traffic (termasuk ke EFWS_API_URL) akan through tailnet, not through GSM directly."
        fi

        # DNS takeover check
        if command -v resolvectl >/dev/null 2>&1; then
            RESOLV_INFO=$(resolvectl status 2>/dev/null || true)
            if echo "$RESOLV_INFO" | grep -q "100.100.100.100"; then
                info "Tailscale MagicDNS (100.100.100.100) aktif sebagai wrong satu DNS server."
                w "If resolusi hostname EFWS_API_URL tiba-tiba lambat/failed padahal connection GSM sehat, coba: sudo tailscale set --accept-dns=false lalu tes again."
            else
                ok "Tailscale not mengambil alih DNS resolver global."
            fi
        fi
    fi
fi

# =============================================================================
# 4. Default route + DNS + reachability real ke EFWS_API_URL
# =============================================================================
log "4. Default route, DNS, dan reachability ke EFWS_API_URL"

ROUTE_INFO=$(ip route get 8.8.8.8 2>&1 || true)
info "$ROUTE_INFO"
ACTIVE_IFACE=$(echo "$ROUTE_INFO" | grep -oP 'dev \K[^ ]+' | head -n1 || true)
info "Interface aktif for internet when ini: ${ACTIVE_IFACE:-not diketahui}"

if [ "$ACTIVE_IFACE" = "cdc-wdm0" ] || echo "$ACTIVE_IFACE" | grep -q "wwan\|cdc-wdm"; then
    ok "Default route through modem GSM (sesuai prioritas that diinginkan)."
elif [ -n "$ACTIVE_IFACE" ]; then
    w "Default route when ini through '$ACTIVE_IFACE' (not GSM). If GSM sedang connected juga, check again route-metric-nya."
fi

# Get EFWS_API_URL from .env project for tes directly
API_URL=$(grep -m1 '^EFWS_API_URL=' "$PROJECT_DIR/.env" 2>/dev/null | cut -d= -f2- | sed -e 's/\r$//' -e "s/^['\"]//" -e "s/['\"]$//")
if [ -z "$API_URL" ]; then
    w "Not menemukan EFWS_API_URL di $PROJECT_DIR/.env -- lewati tes reachability endpoint."
else
    API_HOST=$(echo "$API_URL" | sed -E 's#^[a-zA-Z]+://##; s#[/:].*$##')
    info "Endpoint from .env : $API_URL"
    info "Host that di-resolve: $API_HOST"

    if command -v getent >/dev/null 2>&1; then
        DNS_RESULT=$(getent hosts "$API_HOST" 2>&1 || true)
        if [ -n "$DNS_RESULT" ]; then
            ok "DNS resolve sukses: $DNS_RESULT"
        else
            f "DNS resolve FAILED for $API_HOST. Check resolver aktif (resolvectl status) or APN operator."
        fi
    fi

    if command -v curl >/dev/null 2>&1; then
        HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API_URL" 2>&1 || true)
        if [ -n "$HTTP_CODE" ] && [ "$HTTP_CODE" != "000" ]; then
            ok "Endpoint dapat dihubungi (HTTP $HTTP_CODE) through interface $ACTIVE_IFACE."
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
    info "Ada kegagalan that perlu ditindaklanjuti before yakin jalur komunikasi sehat."
elif [ "$warn" -gt 0 ]; then
    info "None kegagalan fatal, tapi ada beberapa hal for diperiksa manual (see WARN di atas)."
else
    info "All pengecekan lolos."
fi
