# Status bar for the Hyprland session. Config lives in ./waybar and is symlinked to
# ~/.config/waybar (same pattern as hypr/kitty): a small bottom bar with workspaces,
# window title, clock, and CPU/memory/network/volume. Started on session start by the
# hyprland.start hook in hypr/hyprland.lua.
resource "host_package_pacman" "waybar" {
  name = "waybar"
}

resource "host_link" "waybar_config" {
  source      = "waybar"
  destination = "~/.config/waybar"

  depends_on = [
    host_package_pacman.waybar,
  ]
}
