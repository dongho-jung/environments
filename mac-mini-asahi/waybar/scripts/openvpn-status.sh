#!/usr/bin/env sh

set -eu

signin_marker="${XDG_STATE_HOME:-$HOME/.local/state}/waybar/openvpn-1password.signin.pending"

print_json() {
  printf '{"text":"%s","class":"%s"}\n' "$1" "$2"
}

if command -v openvpn3 >/dev/null 2>&1; then
  sessions=$(openvpn3 sessions-list 2>/dev/null || true)
  connected_count=$(printf '%s\n' "$sessions" | awk '
    /Status: .*Client connected/ { count++ }
    END { print count + 0 }
  ')

  if [ "$connected_count" -gt 0 ]; then
    print_json "VPN On" "on"
    exit 0
  fi
fi

if [ -f "$signin_marker" ]; then
  print_json "VPN Off" "off"
  exit 0
fi

tun_devices=$(ip -brief addr 2>/dev/null | awk '
  /^(tun|tap)/ && $2 != "DOWN" {
    list = list (list ? "," : "") $1
  }
  END { print list }
')

if [ -n "$tun_devices" ]; then
  print_json "VPN On" "on"
else
  print_json "VPN Off" "off"
fi
