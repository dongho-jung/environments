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
    devices=$(printf '%s\n' "$sessions" | awk '
      /^-+$/ { device = ""; next }
      /Device:/ {
        for (i = 1; i <= NF; i++) {
          if ($i == "Device:") {
            device = $(i + 1)
          }
        }
      }
      /Status: .*Client connected/ {
        if (device != "") {
          list = list (list ? "," : "") device
        }
      }
      END { print list }
    ')

    if [ "$connected_count" -eq 1 ] && [ -n "$devices" ]; then
      print_json "VPN $devices" "connected"
    else
      print_json "VPN $connected_count" "connected"
    fi
    exit 0
  fi
fi

if [ -f "$signin_marker" ]; then
  print_json "VPN auth" "pending"
  exit 0
fi

tun_devices=$(ip -brief addr 2>/dev/null | awk '
  /^(tun|tap)/ && $2 != "DOWN" {
    list = list (list ? "," : "") $1
  }
  END { print list }
')

if [ -n "$tun_devices" ]; then
  print_json "VPN $tun_devices" "connected"
else
  print_json "VPN off" "disconnected"
fi
