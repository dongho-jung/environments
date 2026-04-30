#!/usr/bin/env bash

set -euo pipefail

WAYBAR_SIGNAL="${WAYBAR_SIGNAL:-8}"

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

if ! command -v hotkey-mode >/dev/null 2>&1; then
  notify_msg "HotKey" "hotkey-mode command not found."
  exit 1
fi

if hotkey-mode toggle >/dev/null 2>&1; then
  refresh_waybar
  exit 0
fi

notify_msg "HotKey" "Failed to toggle."
refresh_waybar
exit 1
