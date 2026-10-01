resource "host_mac_dock_app" "system_settings" {
  path     = "/System/Applications/System Settings.app"
  priority = 10
}

resource "host_mac_dock_folder" "downloads" {
  path     = "~/Downloads"
  priority = 10
}

resource "host_mac_settings" "settings" {
  groups = {
    "com.apple.dock" = {
      autohide                  = true
      "show-recents"            = false
      "minimize-to-application" = false
      "show-process-indicators" = true
      "wvous-br-corner"         = 14
    }

    # Keyboard keys live in keyboard.tf and trackpad keys in trackpad.tf.
    NSGlobalDomain = {
      "com.apple.springing.enabled"        = true
      "com.apple.springing.delay"          = 0.5
      "com.apple.sound.beep.flash"         = 0
      NSAutomaticCapitalizationEnabled     = true
      NSAutomaticPeriodSubstitutionEnabled = true
      NSWindowShouldDragOnGesture          = true
      AppleMiniaturizeOnDoubleClick        = false
    }

    "com.apple.menuextra.clock" = {
      IsAnalog      = true
      ShowAMPM      = true
      ShowDate      = 2
      ShowDayOfWeek = false
    }

    "com.apple.screencapture" = {
      captureDelay = 5
      showsClicks  = true
      style        = "selection"
      video        = true
    }
  }
}
