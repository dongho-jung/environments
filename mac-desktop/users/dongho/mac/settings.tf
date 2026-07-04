resource "host_mac_settings" "settings" {
  groups = {
    "com.apple.dock" = {
      autohide                  = true
      "show-recents"            = false
      "minimize-to-application" = false
      "show-process-indicators" = true
      "wvous-br-corner"         = 14
    }

    NSGlobalDomain = {
      "com.apple.springing.enabled"        = true
      "com.apple.springing.delay"          = 0.5
      "com.apple.sound.beep.flash"         = 0
      "com.apple.keyboard.fnState"         = true
      NSAutomaticCapitalizationEnabled     = true
      NSAutomaticPeriodSubstitutionEnabled = true
      NSWindowShouldDragOnGesture          = true
      AppleMiniaturizeOnDoubleClick        = false
      "com.apple.trackpad.forceClick"      = true
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

    "com.apple.AppleMultitouchTrackpad" = {
      Clicking                = true
      TrackpadThreeFingerDrag = false
      TrackpadRightClick      = true
    }

    "com.apple.driver.AppleBluetoothMultitouch.trackpad" = {
      Clicking                = true
      TrackpadThreeFingerDrag = false
      TrackpadRightClick      = true
    }
  }
}
