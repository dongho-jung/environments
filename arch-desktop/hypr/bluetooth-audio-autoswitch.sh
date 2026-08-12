#!/usr/bin/env bash

# Make a newly connected Bluetooth sink the default only when its BlueZ device
# is explicitly marked Trusted. This replaces PipeWire's broad
# module-switch-on-connect policy, which cannot express a trust-based allowlist.

set -uo pipefail
export LC_ALL=C

readonly app_name="bluetooth-audio-autoswitch"
readonly runtime_dir="${XDG_RUNTIME_DIR:-/tmp}/arch-desktop"

acquire_watch_lock() {
    mkdir -p "$runtime_dir"
    exec 9>"$runtime_dir/$app_name.lock"
    flock -n 9
}

log_message() {
    logger --tag "$app_name" -- "$*" 2>/dev/null || true
}

notify_switch() {
    command -v notify-send >/dev/null 2>&1 || return 0
    notify-send \
        -a "Bluetooth 오디오" \
        "허용된 오디오 장치로 전환" \
        "$1" 2>/dev/null || true
}

get_sink_details() {
    local sink_index="$1"

    pactl --format=json list sinks 2>/dev/null |
        jq -r --argjson sink_index "$sink_index" '
            .[]
            | select(
                .index == $sink_index
                and (.properties["api.bluez5.address"] // "") != ""
              )
            | [
                .name,
                (.description // .name),
                (.properties["api.bluez5.address"] // "")
              ]
            | @tsv
        '
}

is_trusted_address() {
    local address="${1^^}"
    local device_suffix
    local object_path
    local trusted

    [[ "$address" =~ ^([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}$ ]] || return 1
    device_suffix="/dev_${address//:/_}"

    while IFS= read -r object_path; do
        [[ "$object_path" == *"$device_suffix" ]] || continue

        trusted="$(
            busctl --system get-property \
                org.bluez \
                "$object_path" \
                org.bluez.Device1 \
                Trusted 2>/dev/null
        )"
        [[ "$trusted" == "b true" ]]
        return
    done < <(busctl --system tree org.bluez --list --no-pager 2>/dev/null)

    return 1
}

switch_to_sink_if_trusted() {
    local sink_index="$1"
    local details=""
    local sink_name
    local description
    local address
    local current_sink

    # The subscription event can arrive just before the sink is queryable.
    for _ in {1..10}; do
        details="$(get_sink_details "$sink_index")"
        [[ -n "$details" ]] && break
        sleep 0.1
    done
    [[ -n "$details" ]] || return 0

    IFS=$'\t' read -r sink_name description address <<<"$details"
    [[ -n "$sink_name" && -n "$address" ]] || return 0

    if ! is_trusted_address "$address"; then
        log_message "ignored untrusted Bluetooth sink $sink_name ($address)"
        return 0
    fi

    current_sink="$(pactl get-default-sink 2>/dev/null || true)"
    [[ "$current_sink" == "$sink_name" ]] && return 0

    if pactl set-default-sink "$sink_name"; then
        log_message "switched default output to $sink_name ($address)"
        notify_switch "$description"
    fi
}

switch_to_single_connected_trusted_sink() {
    local sink_index
    local details
    local sink_name
    local description
    local address
    local candidate=""

    while IFS= read -r sink_index; do
        [[ "$sink_index" =~ ^[0-9]+$ ]] || continue
        details="$(get_sink_details "$sink_index")"
        [[ -n "$details" ]] || continue
        IFS=$'\t' read -r sink_name description address <<<"$details"
        is_trusted_address "$address" || continue

        # With multiple trusted sinks already present there is no fresh connect
        # event to reveal user intent, so retain the current default.
        [[ -z "$candidate" ]] || return 0
        candidate="$sink_index"
    done < <(
        pactl --format=json list sinks 2>/dev/null |
            jq -r '
                .[]
                | select((.properties["api.bluez5.address"] // "") != "")
                | .index
            '
    )

    if [[ -n "$candidate" ]]; then
        switch_to_sink_if_trusted "$candidate"
    fi

    return 0
}

watch_sinks() {
    local event
    local sink_index

    # Hyprland config reloads must not leave duplicate subscribers behind.
    acquire_watch_lock || exit 0

    while true; do
        if ! pactl info >/dev/null 2>&1; then
            sleep 1
            continue
        fi

        # Covers an allowed earbud that connected before this watcher started.
        switch_to_single_connected_trusted_sink

        while IFS= read -r event; do
            case "$event" in
                "Event 'new' on sink #"*)
                    sink_index="${event##*#}"
                    [[ "$sink_index" =~ ^[0-9]+$ ]] || continue
                    switch_to_sink_if_trusted "$sink_index"
                    ;;
            esac
        done < <(pactl subscribe 2>/dev/null)

        # PipeWire may have restarted; reconnect the subscription without
        # requiring a Hyprland restart.
        sleep 1
    done
}

case "${1:-watch}" in
    --once)
        switch_to_single_connected_trusted_sink
        ;;
    watch)
        watch_sinks
        ;;
    *)
        printf 'Usage: %s [--once]\n' "$0" >&2
        exit 2
        ;;
esac
