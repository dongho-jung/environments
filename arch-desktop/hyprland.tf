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

# Backlight control behind the XF86MonBrightness binds in hyprland.lua. This
# desktop has no backlight device, so the binds are inert here; the package is
# installed anyway to keep the shared hypr config portable to laptops.
resource "host_package_pacman" "brightnessctl" {
  name = "brightnessctl"
}

resource "host_link" "hypr_config" {
  source       = "hypr"
  destination  = "~/.config/hypr"
  stage_source = true

  depends_on = [
    # The private session guard uses GTK layer-shell and Python GObject, which
    # are direct runtime dependencies of these managed desktop packages.
    host_package_aur.waybar,
    host_package_pacman.blueman,
    host_package_pacman.jq,
    host_package_pacman.hyprland,
    host_package_pacman.pipewire_pulse,
    host_link.sunglass,
    host_systemd_service.bluetooth,
  ]
}

# Auto-launch Hyprland on tty1 login through start-hyprland, the recommended
# launcher -- running the Hyprland binary directly triggers a "started without
# start-hyprland" warning (Hyprland >= 0.53). Guarded so only a bare tty1 login
# starts it; other VTs and an existing Wayland session drop to a normal shell.
# exec replaces the login shell, so quitting Hyprland ends the session.
resource "host_file" "zprofile" {
  path = "~/.zprofile"

  content = <<-EOT
    if [ -z "$WAYLAND_DISPLAY" ] && [ "$XDG_VTNR" = 1 ]; then
      exec start-hyprland
    fi
  EOT

  depends_on = [
    host_package_pacman.hyprland,
  ]
}
