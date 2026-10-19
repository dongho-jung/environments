resource "host_mac_settings" "input_source_shortcut" {
  settings = {
    next_input_source = {
      domain = "com.apple.symbolichotkeys"
      key    = "AppleSymbolicHotKeys"
      merge  = true

      value = {
        # Hammerspoon uses the native switcher to activate the input method in
        # the focused app. Direct TIS selection can update only the menu icon.
        "61" = {
          enabled = true
          value = {
            parameters = [32, 49, 786432] # Control-Option-Space
            type       = "standard"
          }
        }
      }
    }
  }
}
