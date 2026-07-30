# Screenshot toolkit for Wayland/Hyprland:
#   grim     - captures the framebuffer
#   slurp    - selects a region to hand to grim
#   hyprshot - Hyprland-native capture wrapper (region/window/output) over grim/slurp
#   hyprpicker - freezes the current frame while a screenshot region is selected
#   satty    - annotation editor (arrows/text/blur); receives the capture on stdin
#   wf-recorder - records a selected region or the focused-window geometry to MP4
#   wayscrollshot - selects and stitches a region while it is manually scrolled
# Bound to the Print-key combinations in hypr/hyprland.lua; Alt+Print starts a
# scrolling capture, while Ctrl variants capture the focused window directly.
resource "host_package_pacman" "grim" {
  name = "grim"
}

resource "host_package_pacman" "slurp" {
  name = "slurp"
}

resource "host_package_pacman" "hyprshot" {
  name = "hyprshot"
}

# `hyprshot --freeze` uses hyprpicker to hold the current frame while a region
# is selected. Hyprshot treats it as optional and silently skips freezing when
# it is absent, so manage it explicitly for the Print binding in hyprland.lua.
resource "host_package_pacman" "hyprpicker" {
  name = "hyprpicker"
}

resource "host_package_pacman" "satty" {
  name = "satty"
}

resource "host_package_pacman" "wf_recorder" {
  name = "wf-recorder"
}

# The prebuilt AUR package avoids compiling the Rust/OpenCV application locally.
resource "host_package_aur" "wayscrollshot" {
  name = "wayscrollshot-bin"

  depends_on = [
    host_aur_helper.yay,
  ]
}
