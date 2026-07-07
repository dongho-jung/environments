# Hyprland Wayland compositor and its first-party companions. The config lives in
# ./hypr and is symlinked to ~/.config/hypr (same pattern as neovim), so both
# hyprland.lua (compositor) and hyprlock.conf (lock screen) are managed together.
resource "host_package_pacman" "hyprland" {
  name = "hyprland"
}

# Application launcher bound to SUPER+R in hyprland.lua (`menu = "hyprlauncher"`).
resource "host_package_pacman" "hyprlauncher" {
  name = "hyprlauncher"
}

# Idle daemon, started via `hl.exec_cmd("hypridle")` on hyprland.start.
resource "host_package_pacman" "hypridle" {
  name = "hypridle"
}

# Lock screen, bound to SUPER+L and used on suspend; configured by hyprlock.conf.
resource "host_package_pacman" "hyprlock" {
  name = "hyprlock"
}

resource "host_link" "hypr_config" {
  source      = "hypr"
  destination = "~/.config/hypr"

  depends_on = [
    host_package_pacman.hyprland,
  ]
}
