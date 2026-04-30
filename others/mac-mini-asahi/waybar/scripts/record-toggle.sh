#!/usr/bin/env sh

set -eu

PIDFILE="/tmp/wf-recorder.pid"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  kill -INT "$(cat "$PIDFILE")"
  rm -f "$PIDFILE"
  pkill -RTMIN+10 waybar
  exit 0
fi

if [ "${1:-}" = "window" ]; then
  eval "$(hyprctl activewindow -j | jq -r '"x=\(.at[0]) y=\(.at[1]) w=\(.size[0]) h=\(.size[1])"')"
  geometry="${x},${y} ${w}x${h}"
else
  geometry=$(slurp 2>/dev/null) || exit 0
fi

today=$(date +%Y-%m-%d)
year=$(date +%Y)
dir="$HOME/videos/$year/$today"
mkdir -p "$dir"

n=1
while [ -f "$dir/$n.mp4" ]; do
  n=$((n + 1))
done

sleep 5
wf-recorder -g "$geometry" -f "$dir/$n.mp4" &
echo $! > "$PIDFILE"
pkill -RTMIN+10 waybar
