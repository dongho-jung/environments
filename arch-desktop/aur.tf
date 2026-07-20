resource "host_package_pacman" "base_devel" {
  name = "base-devel"
}

# AUR packages build untrusted, mutable PKGBUILDs as the target user. Review
# each package before adding it here; this resource only bootstraps the helper.
resource "host_aur_helper" "yay" {
  name = "yay"

  depends_on = [
    host_package_pacman.base_devel,
    host_package_pacman.git,
  ]
}
