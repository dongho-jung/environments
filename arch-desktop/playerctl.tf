# MPRIS media controller, driven by the XF86Audio{Next,Play,Pause,Prev} keybinds
# in hyprland.lua.
resource "host_package_pacman" "playerctl" {
  name = "playerctl"
}
