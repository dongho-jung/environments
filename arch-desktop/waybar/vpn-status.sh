#!/usr/bin/env bash
# waybar custom/vpn module. Emits JSON for the user-locked OpenVPN tunnel state.
# Runs as the normal user; it inspects the process table (world-readable) so no
# root is needed just to read status. Both states are shown explicitly so the bar
# never leaves you guessing.

is_up() {
    local pid
    # Match by exact process name (comm == "openvpn"), NOT full cmdline, so a
    # shell that merely mentions the string does not count as connected. Then
    # confirm it is *our* tunnel via the run-dir marker in its args.
    for pid in $(pgrep -x openvpn 2>/dev/null); do
        if tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q 'openvpn-userlocked'; then
            return 0
        fi
    done
    return 1
}

if is_up; then
    printf '{"text":"🔒 VPN ON","class":"connected","tooltip":"OpenVPN 연결됨 (user-locked) — 우클릭: 해제"}\n'
else
    printf '{"text":"VPN off","class":"disconnected","tooltip":"VPN 연결 안 됨 — 클릭하면 연결"}\n'
fi
