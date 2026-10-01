#!/usr/bin/env bash
# Bring a freshly installed macOS up to this repository's Terraform state in a
# single run. Everything that used to be typed by hand first - Command Line
# Tools, Homebrew, the hashicorp tap, the checkout - is done here, so
# `terraform apply` only has to converge.
#
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/dongho-jung/environments/main/bootstrap.sh)"
#
# or, from a checkout that already exists:
#
#   ./bootstrap.sh
#
# Both things a person has to do are asked for at the top: the sudo password,
# once, and the one paste that puts this machine's SSH key on the GitHub
# account. Everything after that runs unattended. Re-running is safe: every step
# checks for what it would create before creating it.
set -euo pipefail

repo_https=https://github.com/dongho-jung/environments.git
repo_ssh=git@github.com:dongho-jung/environments.git
profile_dir=${BOOTSTRAP_PROFILE:-mac-desktop}
default_checkout=$HOME/projects/environments
expected_user=dongho
ssh_key=$HOME/.ssh/id_ed25519
ssh_key_comment=dongho971220@gmail.com
github_key_page=https://github.com/settings/ssh/new
homebrew_install=https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh
github_key_wait=${BOOTSTRAP_GITHUB_KEY_WAIT:-900}

# Pinned from https://api.github.com/meta so the first clone never has to answer
# an authenticity prompt. mac-desktop/ssh.tf keeps the same keys afterwards.
github_host_keys=(
    'github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl'
    'github.com ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg='
    'github.com ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1aNUkY4Ue1gvwnGLVlOhGeYrnZaMgRK6+PKCUXaDbC7qtbW8gIkhL7aGCsOr/C56SJMy/BCZfxd1nWzAOxSDPgVsmerOBYfNqltV9/hWCqBywINIR+5dIg6JTJ72pcEpEjcYgXkE2YEFXV1JHnsKgbLWNlhScqb2UmyRkQyytRLtL+38TGxkxCflmO+5Z8CSSNY7GidjMIZ7Q4zMjA2n1nGrlTDkzwDCsw+wqFPGQA179cnfGWOWRVruj16z6XyvxvjJwbz0wQZ75XK5tKSb7FNyeIEs4TT4jk+S4dhPeAUC5y+bDYirYgM4GC7uEnztnZyaVWQ7B381AK4Qdrwt51ZqExKbQpTUNn+EjqoTwvqNj4kqx5QUCI0ThS/YkOxJCXmPUWZbhjpCg56i+2aB6CmK2JGhn57K5mj0MNdBXA4/WnwH6XoPWJzK5Nyu2zB3nAZp+S5hpQs+p1vN1/wsjk='
)

action=apply
require_github_key=true
github_key_ready=false
checkout=

if [[ -t 1 && -z ${NO_COLOR:-} && ${TERM:-dumb} != dumb ]]; then
    c_step=$'\033[1;34m'
    c_good=$'\033[1;32m'
    c_warn=$'\033[1;33m'
    c_fail=$'\033[1;31m'
    c_off=$'\033[0m'
else
    c_step= c_good= c_warn= c_fail= c_off=
fi

step() { printf '\n%s==>%s %s\n' "$c_step" "$c_off" "$1"; }
info() { printf '    %s\n' "$1"; }
good() { printf '    %sok%s  %s\n' "$c_good" "$c_off" "$1"; }
warn() { printf '%s!!%s  %s\n' "$c_warn" "$c_off" "$1" >&2; }
die() {
    printf '%sxx%s  %s\n' "$c_fail" "$c_off" "$1" >&2
    exit 1
}

usage() {
    cat <<'EOF'
usage: bootstrap.sh [--plan] [--skip-github-key] [--help]

  --plan              stop after `terraform plan` instead of applying
  --skip-github-key   do not wait for the SSH key to reach GitHub; the private
                      shell-history and vault clones, and everything that
                      depends on them, will fail
  --help              show this message

environment:
  BOOTSTRAP_PROFILE            directory to converge (default: mac-desktop)
  BOOTSTRAP_GITHUB_KEY_WAIT    seconds to wait for the key paste (default: 900)
EOF
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --plan) action=plan ;;
        --skip-github-key) require_github_key=false ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            die "unknown argument: $1"
            ;;
    esac
    shift
done

preflight() {
    [[ $(uname -s) == Darwin ]] || die "this bootstrap only covers macOS; on Arch use arch-desktop"
    [[ $EUID -ne 0 ]] || die "run as $expected_user, not root; Homebrew refuses a root install"
    [[ $(id -un) == "$expected_user" ]] ||
        die "$profile_dir/main.tf pins target_user = \"$expected_user\", but this shell is $(id -un)"
}

announce() {
    step "Setting up $profile_dir on $(hostname -s)"
    info "Anything that needs you happens at the start:"
    info "  * the sudo password, once, unless a timestamp is still valid"
    info "  * one paste of this machine's SSH key into github.com, if it is new"
    info "Everything after that is unattended. macOS asks for a few approvals"
    info "once the apps are installed; those are listed when the run finishes."
}

# --- sudo -------------------------------------------------------------------

sudo_keepalive_pid=

stop_sudo_session() {
    [[ -n $sudo_keepalive_pid ]] || return 0
    kill "$sudo_keepalive_pid" 2>/dev/null || true
    sudo_keepalive_pid=
}

start_sudo_session() {
    step "Authenticating sudo once for the whole run"
    if sudo -n true 2>/dev/null; then
        good "an existing sudo timestamp is still valid"
    else
        # sudo reads the password from the terminal rather than stdin, so this
        # still works when the script arrives through a pipe.
        sudo -v || die "sudo authentication failed; run this from an interactive terminal"
    fi

    # sudo's default timestamp_timeout is five minutes, which a full apply
    # easily outlives - as does standing at the GitHub page below. Refreshing it
    # here is what keeps every later `sudo -n` inside Homebrew and the provider
    # silent.
    local owner=$$
    while kill -0 "$owner" 2>/dev/null; do
        sudo -n true 2>/dev/null || exit 0
        sleep 50
    done &
    sudo_keepalive_pid=$!
    trap stop_sudo_session EXIT INT TERM
}

# --- github -----------------------------------------------------------------

ensure_github_known_hosts() {
    step "Pinning GitHub's SSH host keys"
    local known_hosts=$HOME/.ssh/known_hosts
    mkdir -p "$HOME/.ssh"
    chmod 700 "$HOME/.ssh"
    [[ -f $known_hosts ]] || : >"$known_hosts"
    chmod 600 "$known_hosts"

    local key
    for key in "${github_host_keys[@]}"; do
        grep -qxF "$key" "$known_hosts" || printf '%s\n' "$key" >>"$known_hosts"
    done
    good "~/.ssh/known_hosts answers the authenticity prompt up front"
}

ensure_ssh_key() {
    if [[ ! -f $ssh_key ]]; then
        step "Creating $ssh_key"
        # host_ssh_key.github adopts an existing keypair, so creating it now
        # lets the key reach GitHub before the first apply needs it.
        ssh-keygen -t ed25519 -C "$ssh_key_comment" -f "$ssh_key" -N '' -q
        good "new ed25519 keypair"
    fi

    [[ -f $ssh_key.pub ]] && return 0
    ssh-keygen -y -f "$ssh_key" >"$ssh_key.pub" ||
        die "$ssh_key has no readable public half; move it aside and re-run"
}

github_ssh_works() {
    local out
    out=$(ssh -o BatchMode=yes -o ConnectTimeout=10 -T git@github.com 2>&1) || true
    [[ $out == *"successfully authenticated"* ]]
}

# gh is the shortcut for a machine that is already signed in - a re-run, or a
# Mac where gh came along before this script did. It is never installed just for
# this, because Homebrew does not exist yet at this point in the run.
register_key_with_gh() {
    command -v gh >/dev/null 2>&1 || return 1
    gh auth status >/dev/null 2>&1 || return 1

    local title
    title=$(scutil --get ComputerName 2>/dev/null || hostname -s)
    gh ssh-key add "$ssh_key.pub" --title "$title" >/dev/null 2>&1 || return 1
    github_ssh_works
}

wait_for_github_key() {
    printf '\n'
    info "Paste this public key at $github_key_page:"
    printf '\n%s\n\n' "$(cat "$ssh_key.pub")"

    if pbcopy <"$ssh_key.pub" 2>/dev/null; then
        info "(it is already on the clipboard - just hit Cmd+V in the Key box)"
    fi
    open "$github_key_page" >/dev/null 2>&1 || true

    info "Waiting for github.com to accept it. Ctrl-C stops the run; re-running"
    info "./bootstrap.sh picks up exactly here."

    local started=$SECONDS
    local deadline=$((SECONDS + github_key_wait))
    local reminder=$((SECONDS + 120))
    local interval
    while ((SECONDS < deadline)); do
        # Tight checks while the paste is most likely landing, then back off so
        # a long wait does not knock on github.com every few seconds.
        interval=5
        ((SECONDS - started < 60)) || interval=15
        sleep "$interval"

        github_ssh_works && return 0
        if ((SECONDS >= reminder)); then
            reminder=$((SECONDS + 120))
            info "still waiting on $github_key_page ..."
        fi
    done
    return 1
}

ensure_github_ssh_access() {
    step "Putting this machine's SSH key on the GitHub account"
    if github_ssh_works; then
        github_key_ready=true
        good "github.com already accepts $ssh_key"
        return 0
    fi

    if register_key_with_gh; then
        github_key_ready=true
        good "registered through gh, no paste needed"
        return 0
    fi

    # zsh.tf points HISTFILE into the private shell-history clone, so an apply
    # without this key fails on ~/.zshrc and everything hanging off it.
    if [[ $require_github_key != true ]]; then
        warn "--skip-github-key: continuing without it; the private clones will fail"
        return 0
    fi

    if wait_for_github_key; then
        github_key_ready=true
        good "github.com accepts the key"
        return 0
    fi

    die "github.com still does not accept $ssh_key.pub; register it and re-run ./bootstrap.sh"
}

# --- toolchain --------------------------------------------------------------

ensure_command_line_tools() {
    /usr/bin/xcode-select -p >/dev/null 2>&1 && return 0

    step "Installing the Xcode Command Line Tools"
    # softwareupdate only offers the Command Line Tools while this sentinel
    # exists. That is what turns `xcode-select --install`, which opens a dialog
    # and returns immediately, into an install this script can wait on.
    local sentinel=/tmp/.com.apple.dt.CommandLineTools.installondemand.in-progress
    : >"$sentinel"
    local listing label
    listing=$(softwareupdate --list 2>/dev/null) || true
    rm -f "$sentinel"
    label=$(printf '%s\n' "$listing" |
        awk -F'Label: ' '/^ *\* Label: Command Line Tools/ {print $2}' |
        sort -V | tail -n 1)

    if [[ -n $label ]]; then
        info "installing \"$label\""
        sudo softwareupdate --install "$label" --verbose || true
    fi

    /usr/bin/xcode-select -p >/dev/null 2>&1 && return 0

    warn "the headless install did not finish; falling back to the installer dialog"
    /usr/bin/xcode-select --install >/dev/null 2>&1 || true
    until /usr/bin/xcode-select -p >/dev/null 2>&1; do
        info "waiting for the Command Line Tools installer ..."
        sleep 15
    done
}

load_homebrew_env() {
    local candidate
    for candidate in "${HOMEBREW_PREFIX:-/opt/homebrew}/bin/brew" /opt/homebrew/bin/brew /usr/local/bin/brew; do
        if [[ -x $candidate ]]; then
            eval "$("$candidate" shellenv)"
            return 0
        fi
    done
    command -v brew >/dev/null 2>&1
}

ensure_homebrew() {
    load_homebrew_env && return 0

    step "Installing Homebrew"
    local installer
    installer=$(curl -fsSL "$homebrew_install")
    # NONINTERACTIVE skips the installer's "press RETURN to continue"; its sudo
    # calls land on the timestamp opened above.
    NONINTERACTIVE=1 /bin/bash -c "$installer"
    load_homebrew_env || die "Homebrew was installed but brew is still not on PATH"
}

ensure_terraform() {
    command -v terraform >/dev/null 2>&1 && return 0

    step "Installing Terraform"
    # $profile_dir/terraform.tf declares the same tap, so the formula the
    # provider resolves later is the one installed here.
    brew tap hashicorp/tap
    brew install hashicorp/tap/terraform
}

# --- checkout ---------------------------------------------------------------

resolve_checkout() {
    local here=${BASH_SOURCE[0]:-}
    if [[ -n $here && -f $here ]]; then
        local dir
        dir=$(cd -- "$(dirname -- "$here")" && pwd -P)
        if [[ -f $dir/$profile_dir/main.tf ]]; then
            checkout=$dir
            [[ $checkout == "$default_checkout" ]] ||
                warn "running from $checkout; host_git_repo.environments still manages $default_checkout"
            align_origin_remote
            return 0
        fi
    fi

    checkout=$default_checkout
    if [[ ! -d $checkout/.git ]]; then
        step "Cloning environments into $checkout"
        mkdir -p "$(dirname -- "$checkout")"
        if [[ $github_key_ready == true ]]; then
            git clone "$repo_ssh" "$checkout"
        else
            git clone "$repo_https" "$checkout"
        fi
    fi
    align_origin_remote
}

align_origin_remote() {
    # host_git_repo.environments refuses a checkout whose origin is not the SSH
    # URL it declares, so an HTTPS clone is pointed at it here.
    local current
    current=$(git -C "$checkout" remote get-url origin 2>/dev/null || true)
    [[ $current == "$repo_https" ]] || return 0

    info "pointing origin at $repo_ssh"
    git -C "$checkout" remote set-url origin "$repo_ssh"
}

# --- terraform --------------------------------------------------------------

run_terraform() {
    local dir=$checkout/$profile_dir

    step "terraform init"
    terraform -chdir="$dir" init -input=false

    if [[ $action == plan ]]; then
        step "terraform plan"
        terraform -chdir="$dir" plan -input=false
        return 0
    fi

    step "terraform apply"
    terraform -chdir="$dir" apply -input=false -auto-approve && return 0

    # A first apply on a bare machine can fail on resources that only become
    # reachable once an earlier one is installed. One retry converges those; a
    # real failure still surfaces, from the second run.
    warn "the first apply reported failures; retrying once"
    terraform -chdir="$dir" apply -input=false -auto-approve
}

summary() {
    step "Done"
    info "checkout:  $checkout"
    info "profile:   $profile_dir"
    printf '\n'
    info "macOS still asks for these by hand - no script can approve them:"
    info "  * Karabiner-Elements: allow its background items and driver extension"
    info "  * BlackHole: allow the audio driver, then re-run to build the multi-output device"
    info "  * Hammerspoon, KeyCastr, Shottr, BetterTouchTool: Accessibility / Input Monitoring"
    info "  * Docker Desktop: its privileged helper on first launch"
    printf '\n'
    info "Re-run ./bootstrap.sh after granting them to converge the rest."
}

main() {
    preflight
    announce
    start_sudo_session
    ensure_github_known_hosts
    ensure_ssh_key
    ensure_github_ssh_access
    ensure_command_line_tools
    ensure_homebrew
    ensure_terraform
    resolve_checkout
    run_terraform
    summary
}

main
