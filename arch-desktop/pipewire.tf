# Audio stack for the Wayland session. wireplumber is the session manager and
# provides `wpctl`, which the volume/mute keybinds in hyprland.lua call.
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

# PulseAudio-compatible mixer for selecting streams and per-application levels.
resource "host_package_pacman" "pavucontrol" {
  name = "pavucontrol"
}

# The trusted-device watcher parses PipeWire's PulseAudio-compatible JSON to
# identify the exact Bluetooth sink that appeared.
resource "host_package_pacman" "jq" {
  name = "jq"
}

# Automatic output selection is intentionally handled by
# hypr/bluetooth-audio-autoswitch.sh instead of module-switch-on-connect. The
# latter switches to every newly attached sink, while the watcher admits only
# Bluetooth devices explicitly marked Trusted in BlueZ.
