#!/usr/bin/env sh

set -eu

print_json() {
  printf '{"text":"%s","class":"%s"}\n' "$1" "$2"
}

PIDFILE="/tmp/wf-recorder.pid"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  print_json "REC" "on"
else
  rm -f "$PIDFILE"
  print_json "" "off"
fi
