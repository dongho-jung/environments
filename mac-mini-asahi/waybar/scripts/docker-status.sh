#!/usr/bin/env sh

set -eu

print_json() {
  printf '{"text":"%s","class":"%s"}\n' "$1" "$2"
}

if ! command -v docker >/dev/null 2>&1; then
  print_json "DKR n/a" "unavailable"
  exit 0
fi

if output=$(docker ps -q 2>&1); then
  count=$(printf '%s\n' "$output" | sed '/^$/d' | wc -l | tr -d ' ')
  if [ "$count" -gt 0 ]; then
    print_json "DKR $count" "running"
  else
    print_json "DKR 0" "idle"
  fi
  exit 0
fi

case "$output" in
  *"permission denied"*|*"Got permission denied"*)
    print_json "DKR perm" "denied"
    ;;
  *"Is the docker daemon running"*|*"Cannot connect to the Docker daemon"*|*"error during connect"*)
    print_json "DKR off" "stopped"
    ;;
  *)
    print_json "DKR ?" "error"
    ;;
esac
