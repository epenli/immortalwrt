#!/bin/sh
# Recover an empty, stalled scan on the UFI's shared AP/STA radio.
stalled=0
restore_ap() {
    [ "$paused" = 1 ] || return 0
    paused=0
    [ "$(ubus -t 5 call network.wireless status 2>/dev/null | jsonfilter -e '@.radio0.up')" = true ] || return 0
    ubus -t 5 call hostapd.phy0-ap0 get_status >/dev/null 2>&1 || return 0
    ubus -t 5 call hostapd apsta_state '{"phy":"phy0","up":true,"csa":false}' >/dev/null 2>&1
}
trap 'restore_ap; exit 0' TERM INT
while sleep 30; do
    status="$(ubus -t 5 call wpa_supplicant.phy0-sta0 control '{"command":"STATUS"}' 2>/dev/null | jsonfilter -e '@.result')"
    case "$status" in
        *wpa_state=SCANNING*) ;;
        *) stalled=0; continue ;;
    esac
    [ "$(ubus -t 5 call network.wireless status 2>/dev/null | jsonfilter -e '@.radio0.up')" = true ] || { stalled=0; continue; }
    results="$(ubus -t 5 call wpa_supplicant.phy0-sta0 control '{"command":"SCAN_RESULTS"}' 2>/dev/null | jsonfilter -e '@.result')"
    [ "$results" = "bssid / frequency / signal level / flags / ssid" ] || { stalled=0; continue; }
    ap="$(ubus -t 5 call hostapd.phy0-ap0 get_status 2>/dev/null | jsonfilter -e '@.status')"
    [ "$ap" = ENABLED ] || { stalled=0; continue; }
    stalled=$((stalled + 1))
    [ "$stalled" -ge 4 ] || continue
    stalled=0
    logger -t ufi-wifi-recovery 'Empty scan persisted for 120s; briefly pausing AP to recover STA'
    paused=1
    ubus -t 5 call hostapd apsta_state '{"phy":"phy0","up":false}' >/dev/null 2>&1
    ubus -t 5 call wpa_supplicant.phy0-sta0 control '{"command":"REASSOCIATE"}' >/dev/null 2>&1
    n=0
    while [ "$n" -lt 15 ]; do
        sleep 2
        iw dev phy0-sta0 link 2>/dev/null | grep -q '^Connected to ' && break
        n=$((n + 1))
    done
    restore_ap
    if iw dev phy0-sta0 link 2>/dev/null | grep -q '^Connected to '; then
        logger -t ufi-wifi-recovery 'STA associated; AP restored'
    else
        logger -t ufi-wifi-recovery 'STA still disconnected; AP restored; retry deferred for 10 minutes'
    fi
    sleep 600
done
