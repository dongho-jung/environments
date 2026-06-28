resource "host_dnf_package" "fcitx5" {
  name    = "fcitx5"
  version = "latest"
}

resource "host_dnf_package" "fcitx5_autostart" {
  name    = "fcitx5-autostart"
  version = "latest"
}

resource "host_dnf_package" "fcitx5_hangul" {
  name    = "fcitx5-hangul"
  version = "latest"
}

resource "host_dnf_package" "kcm_fcitx5" {
  name    = "kcm-fcitx5"
  version = "latest"
}
