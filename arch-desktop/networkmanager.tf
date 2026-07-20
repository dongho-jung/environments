# Network stack, tracked and re-creatable like the rest of the host.
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
