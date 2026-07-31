resource "host_package_pacman" "font_noto" {
  name = "noto-fonts"
}

resource "host_package_pacman" "font_noto_cjk" {
  name = "noto-fonts-cjk"
}

resource "host_package_pacman" "font_jetbrains_mono_nerd" {
  name = "ttf-jetbrains-mono-nerd"
}
