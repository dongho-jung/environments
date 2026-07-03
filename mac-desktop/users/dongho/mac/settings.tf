resource "host_mac_settings" "settings" {
  groups = {
    dock = {
      autohide                  = true
      "show-recents"            = false
      "minimize-to-application" = false
      "show-process-indicators" = true
      "wvous-br-corner"         = 14
    }

    global = {
      "com.apple.springing.enabled"        = true
      "com.apple.springing.delay"          = 0.5
      "com.apple.sound.beep.flash"         = 0
      AppleLanguages                       = ["en-JP", "ja-JP", "ko-JP"]
      AppleLocale                          = "en_JP"
      "com.apple.keyboard.fnState"         = true
      NSAutomaticCapitalizationEnabled     = true
      NSAutomaticPeriodSubstitutionEnabled = true
      NSWindowShouldDragOnGesture          = true
      AppleMiniaturizeOnDoubleClick        = false
      "com.apple.trackpad.forceClick"      = true
    }

    "menuextra.clock" = {
      IsAnalog      = true
      ShowAMPM      = true
      ShowDate      = 2
      ShowDayOfWeek = false
    }

    screenshot = {
      captureDelay = 5
      showsClicks  = true
      style        = "selection"
      video        = true
    }

    AppleMultitouchTrackpad = {
      Clicking                = true
      TrackpadThreeFingerDrag = false
      TrackpadRightClick      = true
    }

    "driver.AppleBluetoothMultitouch.trackpad" = {
      Clicking                = true
      TrackpadThreeFingerDrag = false
      TrackpadRightClick      = true
    }
  }
}
