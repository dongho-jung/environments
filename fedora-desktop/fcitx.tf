resource "host_package_dnf" "fcitx5" {
  name    = "fcitx5"
  version = "latest"
}

resource "host_package_dnf" "fcitx5_autostart" {
  name    = "fcitx5-autostart"
  version = "latest"
}

resource "host_package_dnf" "fcitx5_hangul" {
  name    = "fcitx5-hangul"
  version = "latest"
}

resource "host_package_dnf" "kcm_fcitx5" {
  name    = "kcm-fcitx5"
  version = "latest"
}
