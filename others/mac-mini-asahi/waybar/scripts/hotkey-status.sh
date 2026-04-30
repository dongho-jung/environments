#!/usr/bin/env sh

set -eu

print_json() {
  printf '{"text":"%s","class":"%s"}\n' "$1" "$2"
}

if ! command -v hotkey-mode >/dev/null 2>&1; then
  print_json "HK Off" "off"
  exit 0
fi

status=$(hotkey-mode status 2>/dev/null || true)

case "$status" in
  *"HotKey:ON"*)
    print_json "HK On" "on"
    ;;
  *)
    print_json "HK Off" "off"
    ;;
esac
