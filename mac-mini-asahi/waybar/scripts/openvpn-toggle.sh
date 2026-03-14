#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$script_dir/openvpn-common.sh"

if [[ "$(connected_count)" -gt 0 ]]; then
  disconnect_vpn
  notify_msg "VPN" "Disconnected."
  refresh_waybar
  exit 0
fi

set +e
"$script_dir/openvpn-connect.sh"
connect_status=$?
set -e

if [[ "$connect_status" -eq 0 ]]; then
  exit 0
fi

if [[ "$connect_status" -eq 10 ]]; then
  launch_signin_terminal
  refresh_waybar
  exit 0
fi

refresh_waybar
exit "$connect_status"
