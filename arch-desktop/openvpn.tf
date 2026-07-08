resource "host_package_pacman" "openvpn" {
  name = "openvpn"
}

# oathtool generates the time-based OTP that vpn-up feeds to OpenVPN's static
# challenge, so connecting needs no typed authenticator code.
resource "host_package_pacman" "oath_toolkit" {
  name = "oath-toolkit"
}

# hyprlauncher entries (SUPER+D -> "VPN Connect" / "VPN Disconnect"). They call
# the root helpers through a scoped NOPASSWD sudoers rule installed by
# openvpn/setup-root.sh, so selecting an item toggles the tunnel with zero input.
# Terminal=false: no window, no prompts. The helpers, sudoers rule, .ovpn profile
# and the secrets they read are set up by setup-root.sh and deliberately kept out
# of Terraform state (state stores resource content in plaintext).
resource "host_file" "vpn_connect_desktop" {
  path    = "~/.local/share/applications/vpn-connect.desktop"
  content = <<-EOT
    [Desktop Entry]
    Type=Application
    Name=VPN Connect
    GenericName=OpenVPN
    Comment=Connect the OpenVPN tunnel (no input required)
    Icon=network-vpn
    Exec=sudo -n /usr/local/bin/vpn-up
    Terminal=false
    Categories=Network;Security;
    Keywords=vpn;openvpn;connect;
  EOT
}

resource "host_file" "vpn_disconnect_desktop" {
  path    = "~/.local/share/applications/vpn-disconnect.desktop"
  content = <<-EOT
    [Desktop Entry]
    Type=Application
    Name=VPN Disconnect
    GenericName=OpenVPN
    Comment=Disconnect the OpenVPN tunnel
    Icon=network-wired-disconnected
    Exec=sudo -n /usr/local/bin/vpn-down
    Terminal=false
    Categories=Network;Security;
    Keywords=vpn;openvpn;disconnect;
  EOT
}
