# Status bar for the Hyprland session. Config lives in ./waybar and is symlinked to
# ~/.config/waybar (same pattern as hypr/kitty): a small bottom bar with workspaces,
# window title, clock, and CPU/memory/network/volume. Started on session start by the
# hyprland.start hook in hypr/hyprland.lua.
resource "host_package_aur" "waybar" {
  name = "waybar-git"

  # Keep the tested build installed instead of rebuilding on every upstream
  # master change. Upgrade explicitly when a newer git build is wanted.
  ignore_version = true
}

resource "host_link" "waybar_config" {
  source       = "waybar"
  destination  = "~/.config/waybar"
  stage_source = true

  depends_on = [
    host_link.hypr_config,
    host_systemd_service.bluetooth,
    host_package_aur.waybar,
    host_package_pacman.blueman,
  ]
}
