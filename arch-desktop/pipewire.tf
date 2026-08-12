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

# Prefer a newly connected headset or speaker as the default output. Existing
# streams follow the new default through WirePlumber's enabled-by-default
# linking.follow-default-target policy, and fall back when the device vanishes.
resource "host_file" "pipewire_switch_on_connect" {
  path = "~/.config/pipewire/pipewire-pulse.conf.d/switch-on-connect.conf"

  content = <<-EOT
    pulse.cmd = [
      { cmd = "load-module" args = "module-switch-on-connect" }
    ]
  EOT

  depends_on = [
    host_package_pacman.pipewire_pulse,
    host_package_pacman.wireplumber,
  ]
}
