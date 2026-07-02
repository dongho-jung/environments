resource "host_macos_default" "finder_springing_enabled" {
  domain = "NSGlobalDomain"
  key    = "com.apple.springing.enabled"
  bool   = true
}

resource "host_macos_default" "finder_springing_delay" {
  domain = "NSGlobalDomain"
  key    = "com.apple.springing.delay"
  float  = 0.5
}

resource "host_macos_default" "visual_alert_flash_screen" {
  domain = "NSGlobalDomain"
  key    = "com.apple.sound.beep.flash"
  int    = 0
}
