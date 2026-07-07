# Audio stack for the Wayland session. wireplumber is the session manager and
# provides `wpctl`, which the SUPER volume/mute keybinds in hyprland.lua call.
resource "host_package_pacman" "pipewire" {
  name = "pipewire"
}

# PulseAudio-compatible replacement so PulseAudio clients play through PipeWire.
resource "host_package_pacman" "pipewire_pulse" {
  name = "pipewire-pulse"
}

resource "host_package_pacman" "wireplumber" {
  name = "wireplumber"
}
