# Screenshot toolkit for Wayland/Hyprland:
#   grim     - captures the framebuffer
#   slurp    - selects a region to hand to grim
#   hyprshot - Hyprland-native capture wrapper (region/window/output) over grim/slurp
#   satty    - annotation editor (arrows/text/blur); receives the capture on stdin
#   wf-recorder - records a selected Wayland region to MP4
# Bound to the Print keys in hypr/hyprland.lua: `hyprshot -m <mode> --raw | satty -f -`.
resource "host_package_pacman" "grim" {
  name = "grim"
}

resource "host_package_pacman" "slurp" {
  name = "slurp"
}

resource "host_package_pacman" "hyprshot" {
  name = "hyprshot"
}

resource "host_package_pacman" "satty" {
  name = "satty"
}

resource "host_package_pacman" "wf_recorder" {
  name = "wf-recorder"
}
