#!/usr/bin/env bash
# Toggle an interactive region recording. The PID and output path are kept in the
# user's runtime directory so a second invocation stops only the recorder started
# here, without touching another wf-recorder session.
set -euo pipefail

if [[ -n ${XDG_RUNTIME_DIR:-} ]]; then
    state_dir="$XDG_RUNTIME_DIR/arch-desktop"
else
    state_dir="/tmp/arch-desktop-$UID"
fi
pid_file="$state_dir/region-recorder.pid"
output_state_file="$state_dir/region-recorder.output"
log_file="$state_dir/region-recorder.log"
start_lock_file="$state_dir/region-recorder.lock"
recorder_pid=""
action=${1:-toggle}

case $action in
    toggle | status | stop) ;;
    *)
        printf 'usage: %s [toggle|status|stop]\n' "$0" >&2
        exit 2
        ;;
esac

notify_user() {
    if command -v notify-send >/dev/null 2>&1; then
        notify-send -a "화면 녹화" "$@" || true
    fi
}

refresh_waybar() {
    pkill --signal RTMIN+8 --exact waybar 2>/dev/null || true
}

read_recorder_pid() {
    [[ -r $pid_file ]] || return 1
    IFS= read -r recorder_pid < "$pid_file" || return 1
    [[ $recorder_pid =~ ^[0-9]+$ ]]
}

is_our_recorder() {
    local argument output_file

    read_recorder_pid || return 1
    [[ -r /proc/$recorder_pid/comm ]] || return 1
    [[ $(< "/proc/$recorder_pid/comm") == "wf-recorder" ]] || return 1
    [[ -r $output_state_file ]] || return 1
    IFS= read -r output_file < "$output_state_file" || return 1

    while IFS= read -r -d '' argument; do
        [[ $argument == "$output_file" ]] && return 0
    done < "/proc/$recorder_pid/cmdline"
    return 1
}

mkdir -p -- "$state_dir"

if [[ $action == status ]]; then
    if is_our_recorder; then
        printf '{"text":"● REC","class":"recording","tooltip":"영역 화면 녹화 중 — 클릭하면 종료하고 저장합니다."}\n'
    else
        printf '{"text":"","class":"inactive"}\n'
    fi
    exit 0
fi

# Serialize region selection and recorder startup. The lock is released as soon
# as the PID state is ready, so another invocation can still stop the recording.
if ! command -v flock >/dev/null 2>&1; then
    notify_user -u critical "화면 녹화 실패" "flock 명령을 찾을 수 없습니다."
    exit 1
fi
exec {start_lock_fd}> "$start_lock_file"
if ! flock -n "$start_lock_fd"; then
    notify_user "영역 선택 진행 중" "선택을 마치거나 Esc로 취소해 주세요."
    exit 0
fi

if is_our_recorder; then
    kill -INT "$recorder_pid"
    notify_user "화면 녹화 종료 중" "MP4 파일을 마무리하고 있습니다."
    exit 0
fi
rm -f -- "$pid_file" "$output_state_file"
refresh_waybar

if [[ $action == stop ]]; then
    exit 0
fi

for command_name in slurp wf-recorder; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        notify_user -u critical "화면 녹화 실패" "$command_name 명령을 찾을 수 없습니다."
        exit 1
    fi
done

if ! geometry=$(slurp); then
    exit 0
fi
[[ -n $geometry ]] || exit 0

video_root=""
if command -v xdg-user-dir >/dev/null 2>&1; then
    video_root=$(xdg-user-dir VIDEOS 2>/dev/null || true)
fi
# xdg-user-dir returns $HOME when no Videos directory is configured. Keep
# recordings out of the home-directory root in that case.
if [[ -z $video_root || $video_root == "$HOME" ]]; then
    video_root="$HOME/Videos"
fi
output_dir="$video_root/Recordings"
mkdir -p -- "$output_dir"
output_file="$output_dir/recording-$(date +%Y%m%d-%H%M%S-%3N).mp4"

wf-recorder -g "$geometry" -f "$output_file" > "$log_file" 2>&1 &
recorder_pid=$!

# Do not publish the PID while the forked child is still between bash and exec.
# Otherwise a very fast second toggle could reject it by process name and start a
# second recorder. Exec itself should take only a few milliseconds; cap the wait.
recorder_ready=false
for _ in {1..50}; do
    recorder_comm=""
    if [[ -r /proc/$recorder_pid/comm ]]; then
        IFS= read -r recorder_comm < "/proc/$recorder_pid/comm" || true
    fi
    if [[ $recorder_comm == "wf-recorder" ]]; then
        recorder_ready=true
        break
    fi
    kill -0 "$recorder_pid" 2>/dev/null || break
    sleep 0.01
done

if [[ $recorder_ready != true ]]; then
    kill -TERM "$recorder_pid" 2>/dev/null || true
    wait "$recorder_pid" 2>/dev/null || true
    notify_user -u critical "화면 녹화 실패" "로그: $log_file"
    exit 1
fi

printf '%s\n' "$recorder_pid" > "$pid_file"
printf '%s\n' "$output_file" > "$output_state_file"
flock -u "$start_lock_fd"
exec {start_lock_fd}>&-
refresh_waybar

cleanup_state() {
    local saved_pid=""

    if [[ -r $pid_file ]]; then
        IFS= read -r saved_pid < "$pid_file" || true
    fi
    if [[ $saved_pid == "$recorder_pid" ]]; then
        rm -f -- "$pid_file" "$output_state_file"
        refresh_waybar
    fi
}
trap cleanup_state EXIT

notify_user "화면 녹화 시작" "Shift+Print를 다시 누르면 종료합니다."

record_status=0
wait "$recorder_pid" || record_status=$?

if (( record_status == 0 )) && [[ -s $output_file ]]; then
    notify_user "화면 녹화 저장 완료" "$output_file"
    exit 0
fi

notify_user -u critical "화면 녹화 실패" "로그: $log_file"
if (( record_status == 0 )); then
    exit 1
fi
exit "$record_status"
