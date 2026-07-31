resource "host_package_pacman" "base_devel" {
  name = "base-devel"
}

# AUR packages build untrusted, mutable PKGBUILDs as the target user. Review
# each package before adding it; the provider-level aur_helper setting lazily
# bootstraps yay only when an AUR package mutation needs it.

# Migrate the former standalone helper resource out of state without
# uninstalling yay; the provider now treats it as backend tooling.
removed {
  from = host_aur_helper.yay

  lifecycle {
    destroy = false
  }
}
