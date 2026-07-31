# GPU-accelerated terminal, launched by SUPER+return in hyprland.lua (`terminal = "kitty"`).
# Config lives in ./kitty and is symlinked to ~/.config/kitty (same pattern as hypr):
# kitty.conf sets the Jetendard font (Nerd Font glyphs + Korean) so the starship prompt
# glyphs render, and includes the Solarized Light theme.
resource "host_package_pacman" "kitty" {
  name = "kitty"
}

resource "host_link" "kitty_config" {
  source       = "kitty"
  destination  = "~/.config/kitty"
  stage_source = true

  depends_on = [
    host_package_pacman.kitty,
  ]
}
