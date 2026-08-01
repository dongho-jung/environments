# Input method framework, autostarted via `fcitx5 -d` on hyprland.start. The
# hangul engine provides Korean input; the gtk/qt modules wire it into toolkits
# and configtool is the settings GUI.
resource "host_package_pacman" "fcitx5" {
  name = "fcitx5"
}

resource "host_package_pacman" "fcitx5_hangul" {
  name = "fcitx5-hangul"
}

resource "host_package_pacman" "fcitx5_gtk" {
  name = "fcitx5-gtk"
}

resource "host_package_pacman" "fcitx5_qt" {
  name = "fcitx5-qt"
}

resource "host_package_pacman" "fcitx5_configtool" {
  name = "fcitx5-configtool"
}

resource "host_file" "fcitx5_config" {
  path    = "~/.config/fcitx5/config"
  content = file("${path.module}/fcitx5/config")

  depends_on = [
    host_package_pacman.fcitx5,
  ]
}

resource "host_file" "fcitx5_profile" {
  path    = "~/.config/fcitx5/profile"
  content = file("${path.module}/fcitx5/profile")

  depends_on = [
    host_package_pacman.fcitx5,
    host_package_pacman.fcitx5_hangul,
  ]
}

resource "host_file" "fcitx5_hangul_config" {
  path = "~/.config/fcitx5/conf/hangul.conf"
  # Match the blank line Fcitx writes at the end of input-method configs.
  content = format("%s\n", file("${path.module}/fcitx5/conf/hangul.conf"))

  depends_on = [
    host_package_pacman.fcitx5_hangul,
  ]
}

resource "host_file" "fcitx5_quickphrase_config" {
  path    = "~/.config/fcitx5/conf/quickphrase.conf"
  content = file("${path.module}/fcitx5/conf/quickphrase.conf")

  depends_on = [
    host_package_pacman.fcitx5,
  ]
}
