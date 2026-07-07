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

# NOTE: to run docker without sudo, add your user to the `docker` group manually:
#   sudo usermod -aG docker dongho   (then re-login)
# host_user.dongho ignores group changes, so it is left out of Terraform here.
