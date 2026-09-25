# macOS grants Privacy & Security permissions only through an explicit user
# action in System Settings. Terraform cannot perform the grant, so these
# resources record which permission each managed app depends on and report
# whether it is in place. Reading the state needs Full Disk Access for the
# terminal running Terraform; without it every check reports `unknown` and
# prints the pane that grants it.

# The checks below read the privacy database, which that same database
# protects. iTerm2 runs Terraform here, so its Full Disk Access is what turns
# every `unknown` below into a real answer. Terraform works without it.
resource "host_mac_permission" "iterm2_full_disk_access" {
  service  = "full_disk_access"
  client   = "com.googlecode.iterm2"
  required = false

  depends_on = [host_package_brew.iterm2]
}

# Input switching breaks without this: hammerspoon/input-switch.lua drives
# Text Input Source Services from the F16/F17 keys Karabiner produces.
resource "host_mac_permission" "hammerspoon_accessibility" {
  service = "accessibility"
  client  = "org.hammerspoon.Hammerspoon"

  depends_on = [host_package_brew.hammerspoon]
}

# Karabiner remaps Fn and Caps Lock from Karabiner-Core-Service, the process
# macOS lists under Accessibility in Karabiner-Elements 16. The non-privileged
# agents that older versions listed under Input Monitoring no longer run, and
# the virtual keyboard is a driver extension approved separately.
resource "host_mac_permission" "karabiner_accessibility" {
  service = "accessibility"
  client  = "org.pqrs.Karabiner-Core-Service"

  depends_on = [host_package_brew.karabiner_elements]
}

resource "host_mac_permission" "shottr_screen_recording" {
  service  = "screen_recording"
  client   = "cc.ffitch.shottr"
  required = false

  depends_on = [host_package_brew.shottr]
}

resource "host_mac_permission" "keycastr_input_monitoring" {
  service  = "input_monitoring"
  client   = "io.github.keycastr"
  required = false

  depends_on = [host_package_brew.keycastr]
}

resource "host_mac_permission" "bettertouchtool_accessibility" {
  service  = "accessibility"
  client   = "com.hegenberg.BetterTouchTool"
  required = false

  depends_on = [host_package_brew.bettertouchtool]
}
