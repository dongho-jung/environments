# Network stack. Installed by hand during initial setup and adopted here
# (see imports.tf) so it is tracked and re-creatable like everything else.
resource "host_package_pacman" "networkmanager" {
  name = "networkmanager"
}

resource "host_systemd_service" "networkmanager" {
  name    = "NetworkManager.service"
  enabled = true
  running = true

  depends_on = [
    host_package_pacman.networkmanager,
  ]
}
