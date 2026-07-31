resource "host_user" "dongho" {
  name   = "dongho"
  groups = ["docker", "libvirt", "wheel"]

  depends_on = [
    host_package_pacman.docker,
    host_package_pacman.libvirt,
  ]

  lifecycle {
    prevent_destroy = true
  }
}
