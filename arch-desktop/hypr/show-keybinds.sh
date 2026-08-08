#!/usr/bin/env bash

set -euo pipefail

config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/hypr"
style_file="$config_dir/keybinds.css"
runtime_dir="${XDG_RUNTIME_DIR:-/tmp}"
instance="${HYPRLAND_INSTANCE_SIGNATURE:-default}"
instance="${instance//[^[:alnum:]_.-]/_}"
pid_file="$runtime_dir/hypr-keybind-help-$instance.pid"

is_our_wofi() {
    local pid="$1"

    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    [[ -r "/proc/$pid/comm" && -r "/proc/$pid/cmdline" ]] || return 1
    [[ "$(<"/proc/$pid/comm")" == "wofi" ]] || return 1
    tr '\0' '\n' <"/proc/$pid/cmdline" | grep -Fxq -- "$style_file"
}

if [[ -r "$pid_file" ]]; then
    read -r running_pid <"$pid_file" || true
    if is_our_wofi "${running_pid:-}"; then
        kill "$running_pid"
        exit 0
    fi
    rm -f -- "$pid_file"
fi

modifier_names() {
    local mask="$1"
    local -a names=()

    ((mask & 64))  && names+=("SUPER")
    ((mask & 4))   && names+=("CTRL")
    ((mask & 8))   && names+=("ALT")
    ((mask & 1))   && names+=("SHIFT")
    ((mask & 16))  && names+=("MOD2")
    ((mask & 32))  && names+=("MOD3")
    ((mask & 128)) && names+=("MOD5")

    local joined=""
    local name
    for name in "${names[@]}"; do
        [[ -n "$joined" ]] && joined+=" + "
        joined+="$name"
    done
    printf '%s' "$joined"
}

friendly_key() {
    case "${1,,}" in
        return) printf 'Enter' ;;
        left) printf '←' ;;
        right) printf '→' ;;
        up) printf '↑' ;;
        down) printf '↓' ;;
        tab) printf 'Tab' ;;
        prior) printf 'PageUp' ;;
        next) printf 'PageDown' ;;
        grave) printf '%s' '`' ;;
        minus) printf '%s' '-' ;;
        bracketleft) printf '%s' '[' ;;
        bracketright) printf '%s' ']' ;;
        print) printf 'PrintScreen' ;;
        mouse_down) printf 'Wheel Down' ;;
        mouse_up) printf 'Wheel Up' ;;
        mouse:272) printf 'Mouse Left' ;;
        mouse:273) printf 'Mouse Right' ;;
        xf86audioraisevolume) printf 'Volume Up' ;;
        xf86audiolowervolume) printf 'Volume Down' ;;
        xf86audiomute) printf 'Volume Mute' ;;
        xf86audiomicmute) printf 'Mic Mute' ;;
        xf86monbrightnessup) printf 'Brightness Up' ;;
        xf86monbrightnessdown) printf 'Brightness Down' ;;
        xf86audionext) printf 'Media Next' ;;
        xf86audiopause) printf 'Media Pause' ;;
        xf86audioplay) printf 'Media Play' ;;
        xf86audioprev) printf 'Media Previous' ;;
        *) printf '%s' "$1" ;;
    esac
}

raw_bindings="$(
    hyprctl binds | awk '
        $1 == "bind" {
            mask = ""
            key = ""
            description = ""
            next
        }
        $1 == "modmask:" {
            mask = $2
            next
        }
        $1 == "key:" {
            sub(/^[[:space:]]*key:[[:space:]]*/, "")
            key = $0
            next
        }
        $1 == "description:" {
            sub(/^[[:space:]]*description:[[:space:]]*/, "")
            description = $0
            if (description != "")
                print mask "\t" key "\t" description
        }
    '
)"

entries=""
while IFS=$'\t' read -r mask key description; do
    [[ -n "$description" ]] || continue

    mods="$(modifier_names "$mask")"
    key="$(friendly_key "$key")"
    shortcut="$key"
    [[ -n "$mods" ]] && shortcut="$mods + $key"

    printf -v line '%-32s → %s' "$shortcut" "$description"
    entries+="${entries:+$'\n'}$line"
done <<<"$raw_bindings"

if [[ -z "$entries" ]]; then
    entries="단축키 설명을 불러오지 못했습니다."
fi

cleanup() {
    if [[ -r "$pid_file" ]]; then
        read -r recorded_pid <"$pid_file" || true
        [[ "${recorded_pid:-}" == "${menu_pid:-}" ]] && rm -f -- "$pid_file"
    fi
}
trap cleanup EXIT

wofi \
    --dmenu \
    --insensitive \
    --no-custom-entry \
    --cache-file /dev/null \
    --prompt "단축키 검색 · Esc 또는 SUPER+H로 닫기" \
    --width 72% \
    --height 78% \
    --location center \
    --style "$style_file" \
    <<<"$entries" \
    >/dev/null &

menu_pid=$!
printf '%s\n' "$menu_pid" >"$pid_file"
wait "$menu_pid" || true
