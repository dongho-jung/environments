resource "host_package_pacman" "base_devel" {
  name = "base-devel"
}

# AUR packages build untrusted, mutable PKGBUILDs as the target user. Review
# each package before adding it; the provider-level aur_helper setting lazily
# bootstraps yay only when an AUR package mutation needs it.

# Arch enables split debug packages globally. They are not useful on this
# workstation and otherwise leave companions such as yay-debug behind.
resource "host_file" "makepkg_config" {
  path    = "~/.config/pacman/makepkg.conf"
  content = "OPTIONS+=(!debug)\n"
}
