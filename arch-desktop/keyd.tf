# Remap Caps Lock to F17. Fcitx exposes that key as Launch8 and uses it as the
# Korean input toggle, leaving the physical Hangul key free for wl-kbptr.
resource "host_package_pacman" "keyd" {
  name = "keyd"
}

resource "host_system_file" "keyd_default_config" {
  source      = "${path.module}/keyd/default.conf"
  destination = "/etc/keyd/default.conf"

  mode              = "0644"
  adopt_existing    = true
  delete_on_destroy = false

  depends_on = [
    host_package_pacman.keyd,
  ]
}

resource "host_systemd_service" "keyd" {
  name    = "keyd.service"
  enabled = true
  running = true

  depends_on = [
    host_system_file.keyd_default_config,
  ]
}
