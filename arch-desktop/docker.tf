# macOS uses the `docker-desktop` cask (a VM). On Linux, Docker runs natively, so
# this installs the engine + compose plugin and enables the daemon instead.
resource "host_package_pacman" "docker" {
  name = "docker"
}

resource "host_package_pacman" "docker_compose" {
  name = "docker-compose"
}

resource "host_systemd_service" "docker" {
  name    = "docker.service"
  enabled = true
  running = true

  depends_on = [
    host_package_pacman.docker,
  ]
}
