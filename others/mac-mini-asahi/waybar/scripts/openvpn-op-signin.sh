#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$script_dir/openvpn-common.sh"

ensure_state_dir
trap 'rm -f "$OPENVPN_OP_SIGNIN_MARKER"; refresh_waybar' EXIT

load_openvpn_state
account="$(resolve_op_account)"

printf '1Password sign-in for account %s\n\n' "$account"
printf 'If app integration is enabled, approve the request there.\n'
printf 'Otherwise enter your 1Password password here.\n\n'

session_token="$(op signin --account "$account" --raw)"
OPENVPN_OP_SESSION="$session_token"
save_openvpn_state

printf '\n1Password sign-in succeeded. Starting VPN connection...\n'

if "$script_dir/openvpn-connect.sh"; then
  printf 'VPN connection started.\n'
  sleep 1
  exit 0
fi

printf '\nVPN connection did not start. Review the notification and press Enter to close.\n'
read -r _
