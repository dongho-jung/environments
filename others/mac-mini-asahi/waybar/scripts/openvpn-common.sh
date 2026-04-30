#!/usr/bin/env bash

set -euo pipefail

WAYBAR_SIGNAL="${WAYBAR_SIGNAL:-9}"
OPENVPN_CONFIG_PATH="${OPENVPN_CONFIG_PATH:-$HOME/.config/openvpn/client.ovpn}"
OPENVPN_STATE_DIR="${OPENVPN_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/waybar}"
OPENVPN_OP_STATE_FILE="${OPENVPN_OP_STATE_FILE:-$OPENVPN_STATE_DIR/openvpn-1password.env}"
OPENVPN_OP_CONFIG_FILE="${OPENVPN_OP_CONFIG_FILE:-$HOME/.config/waybar/openvpn-1password.conf}"
OPENVPN_OP_SIGNIN_MARKER="${OPENVPN_OP_SIGNIN_MARKER:-$OPENVPN_STATE_DIR/openvpn-1password.signin.pending}"
OPENVPN_OP_MANUAL_CONFIG_DIR="${OPENVPN_OP_MANUAL_CONFIG_DIR:-$OPENVPN_STATE_DIR/op-cli-config}"
OPENVPN_OP_MATCH_REGEX="${OPENVPN_OP_MATCH_REGEX:-openvpn|vpn}"
OPENVPN_CONNECT_TIMEOUT="${OPENVPN_CONNECT_TIMEOUT:-30}"
OPENVPN_KEY_FILE="${OPENVPN_KEY_FILE:-$HOME/.key}"
OPENVPN_KEY_OP_VAR="${OPENVPN_KEY_OP_VAR:-OP}"

ensure_state_dir() {
  mkdir -p "$OPENVPN_STATE_DIR"
  chmod 700 "$OPENVPN_STATE_DIR" >/dev/null 2>&1 || true
}

notify_msg() {
  local summary="$1"
  local body="${2:-}"

  if command -v notify-send >/dev/null 2>&1; then
    notify-send "$summary" "$body"
  else
    printf '%s: %s\n' "$summary" "$body" >&2
  fi
}

refresh_waybar() {
  pkill -RTMIN+"$WAYBAR_SIGNAL" waybar >/dev/null 2>&1 || true
}

connected_count() {
  if ! command -v openvpn3 >/dev/null 2>&1; then
    printf '0\n'
    return
  fi

  openvpn3 sessions-list 2>/dev/null | awk '
    /Status: .*Client connected/ { count++ }
    END { print count + 0 }
  '
}

profile_remote_regex() {
  awk '
    /^remote / {
      host = $2
      gsub(/\./, "[.]", host)
      if (!seen[host]++) {
        hosts = hosts (hosts ? "|" : "") host
      }
    }
    END { print hosts }
  ' "$OPENVPN_CONFIG_PATH"
}

profile_session_paths() {
  local remote_regex
  remote_regex="$(profile_remote_regex)"

  openvpn3 sessions-list 2>/dev/null | awk -v config="$OPENVPN_CONFIG_PATH" -v remote_regex="$remote_regex" '
    function flush(    matches) {
      if (path == "") {
        return
      }

      matches = 0
      if (config_name == config) {
        matches = 1
      } else if (remote_regex != "" && connected_to ~ remote_regex) {
        matches = 1
      }

      if (matches) {
        print path
      }

      path = ""
      config_name = ""
      connected_to = ""
    }

    /^-+$/ { flush(); next }
    NF == 0 { flush(); next }
    $1 == "Path:" { path = $2; next }
    $1 == "Config" && $2 == "name:" { config_name = $3; next }
    $1 == "Connected" && $2 == "to:" { connected_to = $3; next }

    END { flush() }
  ' | awk '!seen[$0]++'
}

disconnect_vpn() {
  local path found=0

  while IFS= read -r path; do
    [[ -n "$path" ]] || continue
    found=1
    openvpn3 session-manage --disconnect --path "$path" >/dev/null 2>&1 || true
  done < <(profile_session_paths)

  openvpn3 session-manage --cleanup >/dev/null 2>&1 || true
  if [[ "$found" -eq 1 ]]; then
    return 0
  fi

  return 1
}

load_openvpn_state() {
  if [[ -f "$OPENVPN_OP_STATE_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$OPENVPN_OP_STATE_FILE"
  fi

  if [[ -f "$OPENVPN_OP_CONFIG_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$OPENVPN_OP_CONFIG_FILE"
  fi
}

save_openvpn_state() {
  ensure_state_dir

  local account="${OPENVPN_OP_ACCOUNT:-}"
  local session="${OPENVPN_OP_SESSION:-}"
  local item="${OPENVPN_OP_ITEM:-}"
  local vault="${OPENVPN_OP_VAULT:-}"
  local use_manual="${OPENVPN_OP_USE_MANUAL_CONFIG:-}"
  local regex="${OPENVPN_OP_MATCH_REGEX:-$OPENVPN_OP_MATCH_REGEX}"

  umask 077
  {
    printf 'export OPENVPN_OP_ACCOUNT=%q\n' "$account"
    printf 'export OPENVPN_OP_SESSION=%q\n' "$session"
    printf 'export OPENVPN_OP_ITEM=%q\n' "$item"
    printf 'export OPENVPN_OP_VAULT=%q\n' "$vault"
    printf 'export OPENVPN_OP_USE_MANUAL_CONFIG=%q\n' "$use_manual"
    printf 'export OPENVPN_OP_MATCH_REGEX=%q\n' "$regex"
  } >"$OPENVPN_OP_STATE_FILE"
}

resolve_op_account() {
  load_openvpn_state

  if [[ -n "${OPENVPN_OP_ACCOUNT:-}" ]]; then
    printf '%s\n' "$OPENVPN_OP_ACCOUNT"
    return 0
  fi

  if [[ -d "$OPENVPN_OP_MANUAL_CONFIG_DIR" ]]; then
    OPENVPN_OP_ACCOUNT="$(op --config "$OPENVPN_OP_MANUAL_CONFIG_DIR" account list --format=json 2>/dev/null | jq -r '.[0].shorthand // empty')"
  fi

  if [[ -z "${OPENVPN_OP_ACCOUNT:-}" ]]; then
    OPENVPN_OP_ACCOUNT="$(op account list --format=json 2>/dev/null | jq -r '.[0].shorthand // empty')"
  fi

  if [[ -z "$OPENVPN_OP_ACCOUNT" ]]; then
    return 1
  fi

  save_openvpn_state
  printf '%s\n' "$OPENVPN_OP_ACCOUNT"
}

op_exec() {
  local -a cmd=(op)

  if [[ "${OPENVPN_OP_USE_MANUAL_CONFIG:-}" == "1" ]]; then
    cmd+=(--config "$OPENVPN_OP_MANUAL_CONFIG_DIR")
  fi

  if [[ -n "${OPENVPN_OP_ACCOUNT:-}" ]]; then
    cmd+=(--account "$OPENVPN_OP_ACCOUNT")
  fi

  if [[ -n "${OPENVPN_OP_SESSION:-}" ]]; then
    cmd+=(--session "$OPENVPN_OP_SESSION")
  fi

  "${cmd[@]}" "$@"
}

auto_signin_with_key_password() {
  local token

  if [[ ! -f "$OPENVPN_KEY_FILE" ]]; then
    return 1
  fi

  if ! token="$("$script_dir/openvpn-op-token.py" 2>/dev/null)"; then
    return 1
  fi

  if [[ -z "$token" ]]; then
    return 1
  fi

  OPENVPN_OP_USE_MANUAL_CONFIG=1
  OPENVPN_OP_SESSION="$token"
  save_openvpn_state
  return 0
}

op_is_ready_noninteractive() {
  resolve_op_account >/dev/null

  if [[ -n "${OPENVPN_OP_SESSION:-}" ]]; then
    if op_exec whoami >/dev/null 2>&1; then
      return 0
    fi

    OPENVPN_OP_SESSION=""
    save_openvpn_state
  fi

  if auto_signin_with_key_password; then
    op_exec whoami >/dev/null 2>&1
    return $?
  fi

  op_exec whoami >/dev/null 2>&1
}

resolve_vpn_item() {
  load_openvpn_state

  if [[ -n "${OPENVPN_OP_ITEM:-}" ]]; then
    return 0
  fi

  local item_json

  item_json="$(
    op_exec item list --categories Login --format=json | jq -cer --arg regex "${OPENVPN_OP_MATCH_REGEX:-$OPENVPN_OP_MATCH_REGEX}" '
      [
        .[]
        | .score = (
            (if (.title // "") | test("capelabs"; "i") then 100 else 0 end)
            + (if (.title // "") | test("openvpn"; "i") then 30 else 0 end)
            + (if (.title // "") | test("vpn"; "i") then 10 else 0 end)
          )
        | select((.title // "") | test($regex; "i"))
      ]
      | sort_by(.score, .title)
      | last // empty
    ' 2>/dev/null || true
  )"

  if [[ -z "$item_json" ]]; then
    return 1
  fi

  OPENVPN_OP_ITEM="$(jq -r '.id // empty' <<<"$item_json")"
  OPENVPN_OP_VAULT="$(jq -r '.vault.id // .vault.name // empty' <<<"$item_json")"

  if [[ -z "$OPENVPN_OP_ITEM" ]]; then
    return 1
  fi

  save_openvpn_state
}

get_vpn_item_json() {
  resolve_op_account >/dev/null
  resolve_vpn_item

  local -a args=(item get "$OPENVPN_OP_ITEM" --format=json --reveal)

  if [[ -n "${OPENVPN_OP_VAULT:-}" ]]; then
    args+=(--vault "$OPENVPN_OP_VAULT")
  fi

  op_exec "${args[@]}"
}

launch_signin_terminal() {
  ensure_state_dir

  if [[ -f "$OPENVPN_OP_SIGNIN_MARKER" ]]; then
    notify_msg "VPN" "1Password sign-in is already waiting in Ghostty."
    return 0
  fi

  : >"$OPENVPN_OP_SIGNIN_MARKER"

  if hyprctl dispatch exec "ghostty --title=1Password-VPN-Signin -e $HOME/.config/waybar/scripts/openvpn-op-signin.sh" >/dev/null 2>&1; then
    notify_msg "VPN" "Ghostty opened for 1Password sign-in."
    return 0
  fi

  rm -f "$OPENVPN_OP_SIGNIN_MARKER"
  notify_msg "VPN" "Could not launch Ghostty for 1Password sign-in."
  return 1
}
