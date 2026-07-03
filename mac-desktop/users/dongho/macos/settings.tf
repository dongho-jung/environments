resource "host_mac_settings" "settings" {
  groups = {
    dock = {
      domain = {
        apple = "dock"
      }

      settings = {
        autohide = {
          key   = "autohide"
          value = true
        }

        show_recents = {
          key   = "show-recents"
          value = false
        }

        minimize_to_application = {
          key   = "minimize-to-application"
          value = false
        }

        show_process_indicators = {
          key   = "show-process-indicators"
          value = true
        }

        bottom_right_hot_corner = {
          key   = "wvous-br-corner"
          value = 14
        }
      }
    }

    global = {
      domain = {
        global = true
      }

      settings = {
        finder_springing_enabled = {
          key   = "com.apple.springing.enabled"
          value = true
        }

        finder_springing_delay = {
          key   = "com.apple.springing.delay"
          value = 0.5
        }

        visual_alert_flash_screen = {
          key   = "com.apple.sound.beep.flash"
          value = 0
        }

        languages = {
          key   = "AppleLanguages"
          value = ["en-JP", "ja-JP", "ko-JP"]
        }

        locale = {
          key   = "AppleLocale"
          value = "en_JP"
        }

        keyboard_fn_state = {
          key   = "com.apple.keyboard.fnState"
          value = true
        }

        keyboard_automatic_capitalization = {
          key   = "NSAutomaticCapitalizationEnabled"
          value = true
        }

        keyboard_automatic_period_substitution = {
          key   = "NSAutomaticPeriodSubstitutionEnabled"
          value = true
        }

        window_drag_on_gesture = {
          key   = "NSWindowShouldDragOnGesture"
          value = true
        }

        window_miniaturize_on_double_click = {
          key   = "AppleMiniaturizeOnDoubleClick"
          value = false
        }

        trackpad_force_click = {
          key   = "com.apple.trackpad.forceClick"
          value = true
        }
      }
    }

    clock = {
      domain = {
        apple = "menuextra.clock"
      }

      settings = {
        analog = {
          key   = "IsAnalog"
          value = true
        }

        show_ampm = {
          key   = "ShowAMPM"
          value = true
        }

        show_date = {
          key   = "ShowDate"
          value = 2
        }

        show_day_of_week = {
          key   = "ShowDayOfWeek"
          value = false
        }
      }
    }

    screenshot = {
      domain = {
        apple = "screencapture"
      }

      settings = {
        capture_delay = {
          key   = "captureDelay"
          value = 5
        }

        show_clicks = {
          key   = "showsClicks"
          value = true
        }

        style = {
          key   = "style"
          value = "selection"
        }

        video = {
          key   = "video"
          value = true
        }
      }
    }

    trackpad = {
      domain = {
        apple = "AppleMultitouchTrackpad"
      }

      settings = {
        tap_to_click = {
          key   = "Clicking"
          value = true
        }

        three_finger_drag = {
          key   = "TrackpadThreeFingerDrag"
          value = false
        }

        right_click = {
          key   = "TrackpadRightClick"
          value = true
        }
      }
    }

    bluetooth_trackpad = {
      domain = {
        apple = "driver.AppleBluetoothMultitouch.trackpad"
      }

      settings = {
        tap_to_click = {
          key   = "Clicking"
          value = true
        }

        three_finger_drag = {
          key   = "TrackpadThreeFingerDrag"
          value = false
        }

        right_click = {
          key   = "TrackpadRightClick"
          value = true
        }
      }
    }
  }
}
