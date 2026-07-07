# Wayland-native dmenu/rofi replacement. Kept available alongside hyprlauncher
# for scripts that expect a dmenu-style picker.
resource "host_package_pacman" "wofi" {
  name = "wofi"
}
