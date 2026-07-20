resource "host_user" "dongho" {
  name   = "dongho"
  groups = ["docker", "wheel"]

  depends_on = [
    host_package_pacman.docker,
  ]

  lifecycle {
    prevent_destroy = true
  }
}
