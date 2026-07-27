#!/usr/bin/env bash

set -euo pipefail

case "${1:-}" in
    increase) delta=20 ;;
    decrease) delta=-20 ;;
    *) exit 2 ;;
esac

# Serialize rapid presses so every 20-point step is applied.
runtime_dir="${XDG_RUNTIME_DIR:-/tmp}"
instance="${HYPRLAND_INSTANCE_SIGNATURE:-default}"
instance="${instance//[^[:alnum:]_.-]/_}"
lock_file="$runtime_dir/hypr-window-opacity-$instance.lock"
exec 9>"$lock_file"
flock 9

# Keep operating on the window that was active when this invocation started.
address="$(hyprctl activewindow -j | jq -r '.address // empty')"
[[ "$address" =~ ^0x[[:xdigit:]]+$ ]] || exit 0
selector="address:$address"

current="$(hyprctl getprop "$selector" opacity)"
[[ "$current" =~ ^([0-9]+([.][0-9]+)?|[.][0-9]+)$ ]] || exit 0
current_percent="$(awk -v opacity="$current" 'BEGIN { printf "%d", int(opacity * 100 + 0.5) }')"
new_percent=$((current_percent + delta))

((new_percent > 100)) && new_percent=100
((new_percent < 20)) && new_percent=20

new_opacity="$(awk -v percent="$new_percent" 'BEGIN { printf "%.2f", percent / 100 }')"

# Use one IPC round trip and set the same exact opacity for focused, unfocused,
# and fullscreen states. The override props keep other opacity rules from
# multiplying the value.
hyprctl eval "
local w = hl.get_window(\"$selector\")
if w then
    local opacity = \"$new_opacity\"
    for _, prop in ipairs({ \"opacity\", \"opacity_inactive\", \"opacity_fullscreen\" }) do
        hl.dispatch(hl.dsp.window.set_prop({ prop = prop, value = opacity, window = w }))
    end
    for _, prop in ipairs({ \"opacity_override\", \"opacity_inactive_override\", \"opacity_fullscreen_override\" }) do
        hl.dispatch(hl.dsp.window.set_prop({ prop = prop, value = \"true\", window = w }))
    end
end
" >/dev/null

hyprctl notify -1 900 "rgb(89b4fa)" "창 불투명도: ${new_percent}%" >/dev/null
