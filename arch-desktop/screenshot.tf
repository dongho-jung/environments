# Screenshot toolkit for Wayland/Hyprland:
#   grim     - captures the framebuffer
#   slurp    - selects a region to hand to grim
#   hyprshot - standalone Hyprland capture CLI (desktop bindings use screenshot.sh)
#   hyprpicker - freezes the current frame while a screenshot region is selected
#   satty    - annotation editor (arrows/text/blur); receives the capture on stdin
#   wf-recorder - records a selected region or the focused-window geometry to MP4
#   wayscrollshot - selects and stitches a region while it is manually scrolled
# Bound to the Print-key combinations in hypr/hyprland.lua; Alt+Print starts a
# scrolling capture, Ctrl+Print captures the focused window, and Ctrl+Alt+Print
# repeats the last successful region/window/output capture at the same geometry.
resource "host_package_pacman" "grim" {
  name = "grim"
}

resource "host_package_pacman" "slurp" {
  name = "slurp"
}

resource "host_package_pacman" "hyprshot" {
  name = "hyprshot"
}

# screenshot.sh uses hyprpicker to hold the current frame while a region is
# selected, so manage it explicitly for the Print binding in hyprland.lua.
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
}
