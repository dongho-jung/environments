#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$script_dir/openvpn-common.sh"

connect_vpn() {
  load_openvpn_state

  if ! op_is_ready_noninteractive; then
    return 10
  fi

  local item_json
  if ! item_json="$(get_vpn_item_json 2>/dev/null)"; then
    notify_msg "VPN" "Could not find a 1Password item matching ${OPENVPN_OP_MATCH_REGEX:-$OPENVPN_OP_MATCH_REGEX}."
    return 11
  fi

  local username password otp
  username="$(jq -r '[.fields[]? | select(.purpose == "USERNAME" or ((.label // "") | ascii_downcase == "username"))][0].value // empty' <<<"$item_json")"
  password="$(jq -r '[.fields[]? | select(.purpose == "PASSWORD" or ((.label // "") | ascii_downcase == "password"))][0].value // empty' <<<"$item_json")"

  if [[ -z "$username" ]]; then
    username="$(awk -F= '/^# OVPN_ACCESS_SERVER_USERNAME=/{print $2; exit}' "$OPENVPN_CONFIG_PATH")"
  fi

  if [[ -z "$username" || -z "$password" ]]; then
    notify_msg "VPN" "The 1Password item is missing username or password."
    return 12
  fi

  local -a otp_args=(item get "$OPENVPN_OP_ITEM" --otp)
  if [[ -n "${OPENVPN_OP_VAULT:-}" ]]; then
    otp_args+=(--vault "$OPENVPN_OP_VAULT")
  fi

  otp="$(op_exec "${otp_args[@]}" 2>/dev/null || true)"

  if [[ -z "$otp" ]]; then
    notify_msg "VPN" "The 1Password item does not expose a primary OTP field."
    return 13
  fi

  disconnect_vpn >/dev/null 2>&1 || true

  local tmpdir auth_file config_file password_b64 otp_b64 scrv1 output
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "${tmpdir:-}"' EXIT

  auth_file="$tmpdir/auth.txt"
  config_file="$tmpdir/config.ovpn"

  password_b64="$(printf '%s' "$password" | base64 | tr -d '\n')"
  otp_b64="$(printf '%s' "$otp" | base64 | tr -d '\n')"
  scrv1="SCRV1:${password_b64}:${otp_b64}"

  printf '%s\n%s\n' "$username" "$scrv1" >"$auth_file"

  awk -v auth_file="$auth_file" '
    /^auth-user-pass([[:space:]].*)?$/ && !done {
      print "auth-user-pass " auth_file
      done = 1
      next
    }
    { print }
    END {
      if (!done) {
        print "auth-user-pass " auth_file
      }
    }
  ' "$OPENVPN_CONFIG_PATH" >"$config_file"

  if output="$(openvpn3 session-start --config "$config_file" --background --timeout "$OPENVPN_CONNECT_TIMEOUT" 2>&1)"; then
    notify_msg "VPN" "Connection started."
    refresh_waybar
    return 0
  fi

  notify_msg "VPN" "$(printf '%s' "$output" | tail -n 1)"
  return 20
}

connect_vpn
