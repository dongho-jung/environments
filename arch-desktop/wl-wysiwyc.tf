# Keyboard-driven clicking for Hyprland, bound to the Hangul key in
# hypr/hyprland.lua. The tool itself is built from ~/projects/wl-wysiwyc and is
# not packaged, so only its config is managed here. Every key in the file is
# optional; these are the ones that differ from the defaults.
resource "host_file" "wl_wysiwyc_config" {
  path = "~/.config/wl-wysiwyc/config.yaml"

  content = <<-EOT
    # wl-wysiwyc. Every key is optional; see docs/configuration.md for the rest.

    keys:
      # Hangul opens the overlay, and while it is up that key belongs to the
      # overlay: pressing it again puts the choices back to how it opened, and
      # pressing it with nothing to undo closes it.
      reset: Hangul

      # Three ways to click, whichever the hand is nearest. Space is one of
      # them, which leaves nothing to swap hints for the grid: set switch to
      # a free key if that is wanted back.
      left_click: ["-", space, enter]
      right_click: "="

      # The letters that are awkward to reach without moving a hand. They are
      # kept out of hints and the grid; the keys around them take their place.
      excluded: tyughvbn
  EOT
}
