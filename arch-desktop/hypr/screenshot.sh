#!/usr/bin/env bash
# Capture with the standard Wayland tools and remember the last successful box.
set -euo pipefail

mode=${1:-region}
case $mode in
    region | window | active-window | output | last) ;;
    *)
        printf 'usage: %s [region|window|active-window|output|last]\n' "$0" >&2
        exit 2
        ;;
esac

notify_user() {
    if command -v notify-send >/dev/null 2>&1; then
        notify-send -a "스크린샷" "$@" || true
    fi
}

umask 077
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/arch-desktop/screenshot"
geometry_file="$state_dir/last-geometry"
mkdir -p -- "$state_dir"
# Serialize selection/capture, but release before opening the annotation editor.
exec 9>"$state_dir/capture.lock"
flock -n 9 || exit 0

picker_pid=""
capture_dir=""
geometry_tmp=""
stop_freeze() {
    if [[ -n $picker_pid ]]; then
        kill "$picker_pid" 2>/dev/null || true
        wait "$picker_pid" 2>/dev/null || true
        picker_pid=""
    fi
}
cleanup() {
    stop_freeze
    [[ -z $capture_dir ]] || rm -rf -- "$capture_dir"
    [[ -z $geometry_tmp ]] || rm -f -- "$geometry_tmp"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

case $mode in
    region)
        # Keep the frozen frame until grim has captured it. Only stop our picker.
        hyprpicker -r -z >/dev/null &
        picker_pid=$!
        sleep 0.2
        geometry=$(slurp -d) || exit 0
        ;;
    output)
        geometry=$(slurp -or) || exit 0
        ;;
    window)
        monitors=$(hyprctl -j monitors)
        boxes=$(hyprctl -j clients | jq -r --argjson monitors "$monitors" '
            .[]
            | select(.mapped == true and .hidden != true)
            | select(.workspace.id as $workspace | any($monitors[];
                .activeWorkspace.id == $workspace or .specialWorkspace.id == $workspace))
            | "\(.at[0]),\(.at[1]) \(.size[0])x\(.size[1])"
        ')
        [[ -n $boxes ]] || exit 0
        geometry=$(slurp -r <<< "$boxes") || exit 0
        ;;
    active-window)
        geometry=$(hyprctl -j activewindow | jq -er '
            select(.mapped == true and .size[0] > 0 and .size[1] > 0)
            | "\(.at[0]),\(.at[1]) \(.size[0])x\(.size[1])"
        ') || exit 0
        ;;
    last)
        if [[ ! -s $geometry_file ]]; then
            notify_user "다시 캡처할 영역 없음" "먼저 PrintScreen으로 영역을 캡처해 주세요."
            exit 0
        fi
        geometry=$(<"$geometry_file")
        ;;
esac

if [[ ! $geometry =~ ^-?[0-9]+,-?[0-9]+\ [1-9][0-9]*x[1-9][0-9]*$ ]]; then
    notify_user "스크린샷 실패" "캡처 영역이 올바르지 않습니다. PrintScreen으로 다시 선택해 주세요."
    exit 1
fi

if [[ $mode == window || $mode == active-window ]]; then
    # Windows can extend beyond the desktop. Clip to its logical bounds, taking
    # monitor scaling and rotation into account, and remember the actual crop.
    geometry=$(hyprctl -j monitors | jq -er --arg geometry "$geometry" '
        map(. + {
            w: ((if (.transform % 2) == 0 then .width else .height end) / .scale | round),
            h: ((if (.transform % 2) == 0 then .height else .width end) / .scale | round)
        }) as $monitors
        | ($geometry | capture("^(?<x>-?[0-9]+),(?<y>-?[0-9]+) (?<w>[0-9]+)x(?<h>[0-9]+)$")
            | map_values(tonumber)) as $box
        | ([$box.x, ($monitors | map(.x) | min)] | max) as $x
        | ([$box.y, ($monitors | map(.y) | min)] | max) as $y
        | ([$box.x + $box.w, ($monitors | map(.x + .w) | max)] | min) as $right
        | ([$box.y + $box.h, ($monitors | map(.y + .h) | max)] | min) as $bottom
        | select($right > $x and $bottom > $y)
        | "\($x),\($y) \($right - $x)x\($bottom - $y)"
    ') || exit 0
fi

capture_dir=$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/arch-screenshot.XXXXXX")
if ! grim -g "$geometry" "$capture_dir/image.png"; then
    stop_freeze
    notify_user "스크린샷 실패" "영역을 캡처하지 못했습니다. PrintScreen으로 다시 선택해 주세요."
    exit 1
fi
stop_freeze

# Commit coordinates only after a successful capture; cancellation or failure
# leaves the previous box intact. Never keep the screenshot itself in state.
geometry_tmp=$(mktemp "$state_dir/geometry.XXXXXX")
printf '%s\n' "$geometry" >"$geometry_tmp"
mv -f -- "$geometry_tmp" "$geometry_file"
geometry_tmp=""
flock -u 9
exec 9>&-

satty -f - --copy-command wl-copy \
    --actions-on-escape=save-to-clipboard,exit --early-exit <"$capture_dir/image.png"
