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

non_interactive=false
case ${1:-} in
    "") ;;
    --non-interactive) non_interactive=true ;;
    *)
        echo "usage: sudo bash $0 [--non-interactive]" >&2
        exit 2
        ;;
esac

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

write_env_file() {
    local user=$1 pass=$2 secret=$3

    umask 077
    tmp_env=$(mktemp "$config_dir/.userlocked.env.XXXXXX")
    trap 'rm -f -- "$tmp_env"' EXIT
    printf 'VPN_USER=%q\nVPN_PASS=%q\nVPN_TOTP_SECRET=%q\n' \
        "$user" "$pass" "$secret" > "$tmp_env"
    chown root:root -- "$tmp_env"
    chmod 600 -- "$tmp_env"
    mv -f -- "$tmp_env" "$env_file"
    trap - EXIT
    validate_root_file "$env_file"
}

migrate_legacy_env() {
    local line legacy_user= legacy_pass= legacy_secret=
    local found_user=false found_pass=false found_secret=false

    validate_root_file "$legacy_env"
    while IFS= read -r line || [[ -n $line ]]; do
        case $line in
            VPN_USER=*)
                [[ $found_user == false ]] || die "$legacy_env contains duplicate VPN_USER"
                legacy_user=${line#VPN_USER=}
                found_user=true
                ;;
            VPN_PASS=*)
                [[ $found_pass == false ]] || die "$legacy_env contains duplicate VPN_PASS"
                legacy_pass=${line#VPN_PASS=}
                found_pass=true
                ;;
            VPN_TOTP_SECRET=*)
                [[ $found_secret == false ]] ||
                    die "$legacy_env contains duplicate VPN_TOTP_SECRET"
                legacy_secret=${line#VPN_TOTP_SECRET=}
                found_secret=true
                ;;
            "") ;;
            *) die "$legacy_env contains an unsupported line" ;;
        esac
    done < "$legacy_env"

    [[ $found_user == true && -n $legacy_user ]] || die "VPN_USER missing in $legacy_env"
    [[ $found_pass == true && -n $legacy_pass ]] || die "VPN_PASS missing in $legacy_env"
    [[ $found_secret == true && -n $legacy_secret ]] ||
        die "VPN_TOTP_SECRET missing in $legacy_env"

    write_env_file "$legacy_user" "$legacy_pass" "$legacy_secret"
    echo "migrated $legacy_env -> $env_file"
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
elif [[ -L $legacy_profile ]]; then
    die "$legacy_profile must not be a symbolic link"
elif [[ -f $legacy_profile ]]; then
    validate_root_file "$legacy_profile"
    install -m 600 -o root -g root -- "$legacy_profile" "$profile"
    validate_root_file "$profile"
    echo "migrated $legacy_profile -> $profile"
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
elif [[ -L $legacy_env ]]; then
    die "$legacy_env must not be a symbolic link"
elif [[ -f $legacy_env ]]; then
    migrate_legacy_env
elif [[ $non_interactive == true ]]; then
    die "no existing secrets found; run without --non-interactive to enter them"
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
    # Bash-escape every value before vpn-up sources this root-only file.
    write_env_file "$u" "$p" "$s"
    echo "wrote $env_file (0600, root-only)"
    if command -v oathtool >/dev/null && oathtool --totp -b "$s" >/dev/null 2>&1; then
        echo "OTP check OK"
    else
        echo "!! oathtool could not parse that TOTP secret; verify it is valid base32"
    fi
fi

if [[ -e $legacy_env || -L $legacy_env || -e $legacy_profile || -L $legacy_profile ]]; then
    echo "NOTE: legacy files under $openvpn_dir/client are no longer used."
    echo "      They were left in place so this migration remains recoverable."
fi

echo
echo "== done =="
echo "Terraform manages /usr/local/bin/vpn-{up,down} and /etc/sudoers.d/vpn."
echo "After terraform apply: sudo -n /usr/local/bin/vpn-up"
echo "Then use Super+R -> 'VPN Connect', or click the waybar VPN pill."
