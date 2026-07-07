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
