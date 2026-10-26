#!/bin/bash
# =============================================================================
# EWS — One-time setup: A7670E over USB (RNDIS) as a permanent 4G uplink
# =============================================================================
# Why this exists:
#   simhata7670e.sh configures the USB network interface by hand (dhclient +
#   `ip route add`). That only lasts until the interface disappears: after a
#   USB replug or a reboot the lease and route are gone and nothing re-runs it.
#
#   This script instead creates a persistent NetworkManager profile that
#   matches the module's USB network driver (rndis_host / cdc_ether / cdc_ncm).
#   NetworkManager then brings the link up by itself every time the module
#   appears (boot, replug, module reset), even if the interface name or MAC
#   changes (some RNDIS modules generate a new MAC on every enumeration).
#
# Run ONCE, while you still have another way in (WiFi SSH or keyboard+monitor):
#   sudo bash scripts/setup_a7670e_usb.sh
#
# Safe to re-run: the profile is recreated from scratch each time.
# =============================================================================

set -u

CONNECTION_NAME="A7670E-USB"
MODEM_METRIC=50      # same priority as EWS-4G in gsm_connect.sh
WIFI_METRIC=600

log() {
    local level="$1"; shift
    printf '[A7670E-USB][%s] %s: %s\n' "$(date '+%H:%M:%S')" "$level" "$*"
}

if [ "$(id -u)" -ne 0 ]; then
    log FAIL "Run with sudo: sudo bash $0"
    exit 1
fi

if ! systemctl is-active --quiet NetworkManager; then
    log FAIL "NetworkManager is not running. This setup needs NetworkManager (Raspberry Pi OS Bookworm default)."
    exit 1
fi

# -----------------------------------------------------------------------------
# STEP 1: Find the module's USB network interface by driver, not by name
# -----------------------------------------------------------------------------
IFACE=""
for i in $(seq 1 30); do
    for dev in /sys/class/net/*; do
        drv=$(basename "$(readlink -f "$dev/device/driver" 2>/dev/null)" 2>/dev/null || true)
        case "$drv" in
            rndis_host|cdc_ether|cdc_ncm)
                IFACE=$(basename "$dev")
                break 2
                ;;
        esac
    done
    log INFO "Waiting for the A7670E USB network interface... ($i/30)"
    sleep 2
done

if [ -z "$IFACE" ]; then
    log FAIL "No RNDIS/ECM interface found. Check the USB cable and that the module is powered."
    log INFO "Debug: ip link; dmesg | grep -i -E 'rndis|cdc_ether|usb'"
    exit 1
fi

MAC=$(cat "/sys/class/net/$IFACE/address")
log OK "Interface: $IFACE (driver: $drv, MAC: $MAC)"

# -----------------------------------------------------------------------------
# STEP 2: Remove leftovers from simhata7670e.sh (manual dhclient fights NM)
# -----------------------------------------------------------------------------
pkill -f "dhclient.*$IFACE" 2>/dev/null && log INFO "Stopped a manual dhclient on $IFACE"
ip route del default via 192.168.0.1 dev "$IFACE" 2>/dev/null && log INFO "Removed the manual default route via 192.168.0.1"

# -----------------------------------------------------------------------------
# STEP 3: Create the persistent NetworkManager profile
# -----------------------------------------------------------------------------
nmcli device set "$IFACE" managed yes

if nmcli connection show "$CONNECTION_NAME" >/dev/null 2>&1; then
    nmcli connection delete "$CONNECTION_NAME" >/dev/null
fi

if ! nmcli connection add type ethernet ifname "*" con-name "$CONNECTION_NAME" \
        match.driver "$drv" \
        connection.autoconnect yes \
        connection.autoconnect-priority 100 \
        ipv4.method auto \
        ipv4.route-metric "$MODEM_METRIC" \
        ipv6.method ignore >/dev/null; then
    log FAIL "Could not create the NetworkManager profile $CONNECTION_NAME"
    exit 1
fi
log OK "Profile $CONNECTION_NAME created (matches driver $drv, metric $MODEM_METRIC)"

# WiFi stays as a lower-priority backup
nmcli -t -f NAME,TYPE connection show | grep ":802-11-wireless" | cut -d: -f1 | while read -r WIFI_NAME; do
    [ -n "$WIFI_NAME" ] || continue
    nmcli connection modify "$WIFI_NAME" ipv4.route-metric "$WIFI_METRIC" ipv6.route-metric "$WIFI_METRIC" \
        && log INFO "WiFi backup: $WIFI_NAME (metric $WIFI_METRIC)"
done

# -----------------------------------------------------------------------------
# STEP 4: Bring it up and verify
# -----------------------------------------------------------------------------
if ! nmcli connection up "$CONNECTION_NAME" >/dev/null 2>&1; then
    log FAIL "nmcli connection up failed. See: journalctl -u NetworkManager -n 50"
    exit 1
fi

IP=$(ip -4 -o addr show dev "$IFACE" | awk '{print $4}' | head -n1)
log OK "IP on $IFACE: ${IP:-none}"

if ping -I "$IFACE" -c 3 -W 3 8.8.8.8 >/dev/null 2>&1; then
    log OK "Internet reachable through $IFACE"
else
    log FAIL "No internet through $IFACE. The module may not have a data session yet (signal / APN / power)."
fi

log INFO "Route to 8.8.8.8: $(ip route get 8.8.8.8 2>&1 | head -n1)"
log INFO "Done. From now on NetworkManager reconnects $CONNECTION_NAME automatically on boot/replug."
exit 0
