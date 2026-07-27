# Screenshot toolkit for Wayland/Hyprland:
#   grim     - captures the framebuffer
#   slurp    - selects a region to hand to grim
#   hyprshot - Hyprland-native capture wrapper (region/window/output) over grim/slurp
#   satty    - annotation editor (arrows/text/blur); receives the capture on stdin
#   wf-recorder - records a selected region or the focused-window geometry to MP4
# Bound to the Print-key combinations in hypr/hyprland.lua; Ctrl variants capture
# the focused window without requiring a click or region selection.
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
