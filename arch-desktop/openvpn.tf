resource "host_package_pacman" "openvpn" {
  name = "openvpn"
}

# oathtool generates the time-based OTP that vpn-up feeds to OpenVPN's static
# challenge, so connecting needs no typed authenticator code.
resource "host_package_pacman" "oath_toolkit" {
  name = "oath-toolkit"
}

# Root-owned launchers are source-backed, so their bytes are checksum-tracked
# without being copied into Terraform state.
resource "host_system_file" "vpn_up" {
  source      = "${path.module}/openvpn/vpn-up"
  destination = "/usr/local/bin/vpn-up"

  mode              = "0755"
  adopt_existing    = true
  delete_on_destroy = true

  depends_on = [
    host_package_pacman.oath_toolkit,
    host_package_pacman.openvpn,
    host_package_pacman.sudo,
  ]
}

resource "host_system_file" "vpn_down" {
  source      = "${path.module}/openvpn/vpn-down"
  destination = "/usr/local/bin/vpn-down"

  mode              = "0755"
  adopt_existing    = true
  delete_on_destroy = true

  depends_on = [
    host_package_pacman.openvpn,
    host_package_pacman.sudo,
  ]
}

# Each command is rendered with sudoers' exact no-argument marker, so this does
# not grant arbitrary arguments to either root wrapper.
resource "host_sudoers_rule" "vpn" {
  name = "vpn"
  user = "dongho"

  commands = [
    host_system_file.vpn_up.destination,
    host_system_file.vpn_down.destination,
  ]

  run_as            = "root"
  nopasswd          = true
  adopt_existing    = true
  delete_on_destroy = true
}

# hyprlauncher entries (SUPER+D -> "VPN Connect" / "VPN Disconnect"). They call
# the Terraform-managed root helpers through a scoped NOPASSWD rule, so selecting
# an item toggles the tunnel with zero input. Terminal=false: no window, no prompts.
# setup-root.sh still handles only the .ovpn profile and root-only secrets, which
# deliberately stay out of Terraform state.
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

  depends_on = [
    host_sudoers_rule.vpn,
  ]
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

  depends_on = [
    host_sudoers_rule.vpn,
  ]
}
