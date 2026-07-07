# AdGuard Home — network-wide ads/trackers blocking DNS server (official `extra`
# package). It ships `adguardhome.service`; enable + start it like docker/cronie
# so the daemon runs on boot. First launch serves a setup wizard on
# http://127.0.0.1:3000 to set the admin login and upstream DNS; afterwards it
# answers DNS on port 53 (point the system resolver at 127.0.0.1 to use it).
resource "host_package_pacman" "adguardhome" {
  name = "adguardhome"
}

resource "host_systemd_service" "adguardhome" {
  name    = "adguardhome.service"
  enabled = true
  running = true

  depends_on = [
    host_package_pacman.adguardhome,
  ]
}
