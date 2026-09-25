resource "host_mac_settings" "keyboard" {
  groups = {
    NSGlobalDomain = {
      # F1-F12 act as standard function keys; the media controls need Fn.
      "com.apple.keyboard.fnState" = true
    }
  }

  settings = {
    # `merge` manages only the shortcuts listed below and leaves the rest of
    # AppleSymbolicHotKeys alone. macOS reads this table at login, so a change
    # applies after logging out and back in, or after running
    # /System/Library/PrivateFrameworks/SystemAdministration.framework/Resources/activateSettings -u
    screenshot_shortcuts = {
      domain = "com.apple.symbolichotkeys"
      key    = "AppleSymbolicHotKeys"
      merge  = true

      value = {
        # Shottr owns Cmd+Shift+3 and Cmd+Shift+4, so the built-in screenshot
        # shortcuts stay off and never race with it.
        # Save picture of screen as a file.
        "28" = {
          enabled = false
          value = {
            parameters = [51, 20, 1179648]
            type       = "standard"
          }
        }
        # Copy picture of screen to the clipboard.
        "29" = {
          enabled = false
          value = {
            parameters = [51, 20, 1441792]
            type       = "standard"
          }
        }
        # Save picture of selected area as a file.
        "30" = {
          enabled = false
          value = {
            parameters = [52, 21, 1179648]
            type       = "standard"
          }
        }
        # Copy picture of selected area to the clipboard.
        "31" = {
          enabled = false
          value = {
            parameters = [52, 21, 1441792]
            type       = "standard"
          }
        }
        # The Dock is permanently hidden by system.tf, so Cmd+Opt+D must not
        # toggle it back.
        "52" = {
          enabled = false
          value = {
            parameters = [100, 2, 1572864]
            type       = "standard"
          }
        }
      }
    }
  }
}
