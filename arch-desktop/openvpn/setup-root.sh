#!/usr/bin/bash
# One-time secret/profile setup for the zero-input OpenVPN launcher. Run with:
#   sudo bash openvpn/setup-root.sh
#
# Copies the .ovpn profile into /etc and interactively writes the root-only
# secrets file. Terraform manages the vpn-up/vpn-down wrappers and their scoped
# sudoers rule; secrets typed here never touch git or Terraform state.
PATH=/usr/bin:/usr/sbin:/bin:/sbin
export PATH
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "run with sudo: sudo bash $0"; exit 1; }

target_user=${SUDO_USER:-dongho}
openvpn_dir=/etc/openvpn
config_dir=$openvpn_dir/userlocked
env_file=$config_dir/userlocked.env
profile=$config_dir/profile.ovpn
download=/home/$target_user/Downloads/profile-userlocked.ovpn
legacy_env=$openvpn_dir/client/userlocked.env
legacy_profile=$openvpn_dir/client/profile-userlocked.ovpn

die() { echo "setup-root: $*" >&2; exit 1; }

validate_root_directory() {
    local path=$1 uid gid mode
    [[ ! -L $path && -d $path ]] || die "$path must be a real directory"
    read -r uid gid mode < <(stat -Lc '%u %g %a' -- "$path") || die "cannot inspect $path"
    [[ $uid == 0 && $gid == 0 && $mode == 700 ]] ||
        die "$path must be root:root mode 0700 (got uid=$uid gid=$gid mode=$mode)"
}

validate_root_file() {
    local path=$1 uid gid mode
    [[ ! -L $path && -f $path ]] || die "$path must be a real regular file"
    read -r uid gid mode < <(stat -Lc '%u %g %a' -- "$path") || die "cannot inspect $path"
    [[ $uid == 0 && $gid == 0 && $mode == 600 ]] ||
        die "$path must be root:root mode 0600 (got uid=$uid gid=$gid mode=$mode)"
}

[[ ! -L $openvpn_dir && -d $openvpn_dir ]] || die "$openvpn_dir must be a real directory"
read -r parent_uid parent_gid parent_mode < <(stat -Lc '%u %g %a' -- "$openvpn_dir") ||
    die "cannot inspect $openvpn_dir"
(( parent_uid == 0 && parent_gid == 0 && (8#$parent_mode & 0022) == 0 )) ||
    die "$openvpn_dir must be root:root and not writable by group or other users"

if [[ -L $config_dir ]] || [[ -e $config_dir && ! -d $config_dir ]]; then
    die "$config_dir exists but is not a real directory"
fi
install -d -m 700 -o root -g root -- "$config_dir"
validate_root_directory "$config_dir"

echo "== profile =="
if [[ -L $profile ]]; then
    die "$profile must not be a symbolic link"
elif [[ -f $profile ]]; then
    validate_root_file "$profile"
    echo "profile already present: $profile"
elif [[ -L $download ]]; then
    die "$download must not be a symbolic link"
elif [[ -f $download ]]; then
    install -m 600 -o root -g root -- "$download" "$profile"
    validate_root_file "$profile"
    echo "copied $download -> $profile"
else
    die "profile not found at $download"
fi

echo "== secrets =="
if [[ -L $env_file ]]; then
    die "$env_file must not be a symbolic link"
elif [[ -f $env_file ]]; then
    validate_root_file "$env_file"
    echo "env file already exists: $env_file (leaving as-is; edit manually to change)"
else
    read -rp  "VPN username              : " u
    read -rsp "VPN password              : " p; echo
    read -rsp "TOTP secret or otpauth:// : " s; echo
    # 1Password often gives a full otpauth:// URI; pull out the secret= from it.
    if [[ $s == otpauth://* ]]; then
        s=$(printf '%s' "$s" | sed -n 's/.*[?&]secret=\([^&]*\).*/\1/p')
    fi
    # Canonical base32: drop spaces, upper-case.
    s=$(printf '%s' "$s" | tr -d '[:space:]' | tr 'a-z' 'A-Z')
    umask 077
    # Bash-escape every value before vpn-up sources this root-only file.
    tmp_env=$(mktemp "$config_dir/.userlocked.env.XXXXXX")
    trap 'rm -f -- "$tmp_env"' EXIT
    printf 'VPN_USER=%q\nVPN_PASS=%q\nVPN_TOTP_SECRET=%q\n' "$u" "$p" "$s" > "$tmp_env"
    chown root:root -- "$tmp_env"
    chmod 600 -- "$tmp_env"
    mv -f -- "$tmp_env" "$env_file"
    trap - EXIT
    validate_root_file "$env_file"
    echo "wrote $env_file (0600, root-only)"
    if command -v oathtool >/dev/null && oathtool --totp -b "$s" >/dev/null 2>&1; then
        echo "OTP check OK"
    else
        echo "!! oathtool could not parse that TOTP secret; verify it is valid base32"
    fi
fi

if [[ -e $legacy_env || -L $legacy_env || -e $legacy_profile || -L $legacy_profile ]]; then
    echo "NOTE: legacy files under $openvpn_dir/client are no longer used."
    echo "      Remove them manually only after the new launcher works."
fi

echo
echo "== done =="
echo "Terraform manages /usr/local/bin/vpn-{up,down} and /etc/sudoers.d/vpn."
echo "After terraform apply: sudo -n /usr/local/bin/vpn-up"
echo "Then use Super+R -> 'VPN Connect', or click the waybar VPN pill."
