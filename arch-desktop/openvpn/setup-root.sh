#!/usr/bin/env bash
# One-time root setup for the zero-input OpenVPN launcher. Run with:
#   sudo bash openvpn/setup-root.sh
#
# Installs the vpn-up / vpn-down helpers, a scoped NOPASSWD sudoers rule, copies
# the .ovpn profile into /etc, and interactively writes the root-only secrets
# file. Secrets are typed here and never touch git or Terraform state.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "run with sudo: sudo bash $0"; exit 1; }

src_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
target_user=${SUDO_USER:-dongho}
etc_dir=/etc/openvpn/client
env_file=$etc_dir/userlocked.env
profile=$etc_dir/profile-userlocked.ovpn
download=/home/$target_user/Downloads/profile-userlocked.ovpn

echo "== installing helpers to /usr/local/bin =="
install -m 755 "$src_dir/vpn-up"   /usr/local/bin/vpn-up
install -m 755 "$src_dir/vpn-down" /usr/local/bin/vpn-down

echo "== installing NOPASSWD sudoers rule =="
tmp_sudo=$(mktemp)
printf '%s ALL=(root) NOPASSWD: /usr/local/bin/vpn-up, /usr/local/bin/vpn-down\n' "$target_user" > "$tmp_sudo"
# Validate before installing so a typo can never lock sudo.
visudo -cf "$tmp_sudo"
install -m 440 -o root -g root "$tmp_sudo" /etc/sudoers.d/vpn
rm -f "$tmp_sudo"

install -d -m 700 "$etc_dir"

echo "== profile =="
if [[ -f $profile ]]; then
    echo "profile already present: $profile"
elif [[ -f $download ]]; then
    install -m 600 "$download" "$profile"
    echo "copied $download -> $profile"
else
    echo "!! profile not found at $download"
    echo "   copy your .ovpn to $profile (chmod 600) and re-run."
fi

echo "== secrets =="
if [[ -f $env_file ]]; then
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
    printf 'VPN_USER=%s\nVPN_PASS=%s\nVPN_TOTP_SECRET=%s\n' "$u" "$p" "$s" > "$env_file"
    chmod 600 "$env_file"
    echo "wrote $env_file (0600, root-only)"
    if command -v oathtool >/dev/null && oathtool --totp -b "$s" >/dev/null 2>&1; then
        echo "OTP check OK — current code: $(oathtool --totp -b "$s")"
    else
        echo "!! oathtool could not parse that TOTP secret; verify it is valid base32"
    fi
fi

echo
echo "== done =="
echo "Test now:  sudo -n /usr/local/bin/vpn-up   # should connect with no prompt"
echo "Then use Super+R -> 'VPN Connect', or click the waybar VPN pill."
