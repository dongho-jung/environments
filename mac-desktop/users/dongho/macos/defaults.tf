resource "host_macos_defaults" "settings" {
  defaults = {
    dock_autohide = {
      domain = "com.apple.dock"
      key    = "autohide"
      bool   = true
    }

    dock_show_recents = {
      domain = "com.apple.dock"
      key    = "show-recents"
      bool   = false
    }

    dock_minimize_to_application = {
      domain = "com.apple.dock"
      key    = "minimize-to-application"
      bool   = false
    }

    dock_show_process_indicators = {
      domain = "com.apple.dock"
      key    = "show-process-indicators"
      bool   = true
    }

    dock_bottom_right_hot_corner = {
      domain = "com.apple.dock"
      key    = "wvous-br-corner"
      int    = 14
    }

    finder_springing_enabled = {
      domain = "NSGlobalDomain"
      key    = "com.apple.springing.enabled"
      bool   = true
    }

    finder_springing_delay = {
      domain = "NSGlobalDomain"
      key    = "com.apple.springing.delay"
      float  = 0.5
    }

    visual_alert_flash_screen = {
      domain = "NSGlobalDomain"
      key    = "com.apple.sound.beep.flash"
      int    = 0
    }

    clock_analog = {
      domain = "com.apple.menuextra.clock"
      key    = "IsAnalog"
      bool   = true
    }

    clock_show_ampm = {
      domain = "com.apple.menuextra.clock"
      key    = "ShowAMPM"
      bool   = true
    }

    clock_show_date = {
      domain = "com.apple.menuextra.clock"
      key    = "ShowDate"
      int    = 2
    }

    clock_show_day_of_week = {
      domain = "com.apple.menuextra.clock"
      key    = "ShowDayOfWeek"
      bool   = false
    }

    languages = {
      domain      = "NSGlobalDomain"
      key         = "AppleLanguages"
      string_list = ["en-JP", "ja-JP", "ko-JP"]
    }

    locale = {
      domain = "NSGlobalDomain"
      key    = "AppleLocale"
      string = "en_JP"
    }

    keyboard_fn_state = {
      domain = "NSGlobalDomain"
      key    = "com.apple.keyboard.fnState"
      bool   = true
    }

    keyboard_automatic_capitalization = {
      domain = "NSGlobalDomain"
      key    = "NSAutomaticCapitalizationEnabled"
      bool   = true
    }

    keyboard_automatic_period_substitution = {
      domain = "NSGlobalDomain"
      key    = "NSAutomaticPeriodSubstitutionEnabled"
      bool   = true
    }

    window_drag_on_gesture = {
      domain = "NSGlobalDomain"
      key    = "NSWindowShouldDragOnGesture"
      bool   = true
    }

    window_miniaturize_on_double_click = {
      domain = "NSGlobalDomain"
      key    = "AppleMiniaturizeOnDoubleClick"
      bool   = false
    }

    screenshot_capture_delay = {
      domain = "com.apple.screencapture"
      key    = "captureDelay"
      float  = 5
    }

    screenshot_show_clicks = {
      domain = "com.apple.screencapture"
      key    = "showsClicks"
      bool   = true
    }

    screenshot_style = {
      domain = "com.apple.screencapture"
      key    = "style"
      string = "selection"
    }

    screenshot_video = {
      domain = "com.apple.screencapture"
      key    = "video"
      bool   = true
    }

    trackpad_tap_to_click = {
      domain = "com.apple.AppleMultitouchTrackpad"
      key    = "Clicking"
      bool   = true
    }

    trackpad_three_finger_drag = {
      domain = "com.apple.AppleMultitouchTrackpad"
      key    = "TrackpadThreeFingerDrag"
      bool   = false
    }

    trackpad_right_click = {
      domain = "com.apple.AppleMultitouchTrackpad"
      key    = "TrackpadRightClick"
      bool   = true
    }

    trackpad_force_click = {
      domain = "NSGlobalDomain"
      key    = "com.apple.trackpad.forceClick"
      bool   = true
    }

    bluetooth_trackpad_tap_to_click = {
      domain = "com.apple.driver.AppleBluetoothMultitouch.trackpad"
      key    = "Clicking"
      bool   = true
    }

    bluetooth_trackpad_three_finger_drag = {
      domain = "com.apple.driver.AppleBluetoothMultitouch.trackpad"
      key    = "TrackpadThreeFingerDrag"
      bool   = false
    }

    bluetooth_trackpad_right_click = {
      domain = "com.apple.driver.AppleBluetoothMultitouch.trackpad"
      key    = "TrackpadRightClick"
      bool   = true
    }
  }
}
