# Notification daemon for Wayland. Config lives in ./mako and is symlinked to
# ~/.config/mako (same pattern as hypr/kitty); mako/config sets a 5s auto-dismiss
# timeout so notifications don't pile up.
resource "host_package_pacman" "mako" {
  name = "mako"
}

resource "host_link" "mako_config" {
  source      = "mako"
  destination = "~/.config/mako"

  depends_on = [
    host_package_pacman.mako,
  ]
}
