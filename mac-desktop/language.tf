# The system runs in Japanese and the keyboard cycles ABC, Japanese romaji, and
# 2-set Korean. hammerspoon/input-switch.lua selects those sources through Text
# Input Source Services from the F16/F17 keys Karabiner produces, so the list
# below is what that script expects to find enabled.
#
# macOS reads the enabled sources when a session starts. A change here applies
# after logging out and back in, and the running input daemon can rewrite the
# key in the meantime, so treat this as the declaration a fresh machine
# converges to rather than a live switch.
resource "host_mac_settings" "language" {
  groups = {
    NSGlobalDomain = {
      AppleLanguages = ["ja-JP"]
      AppleLocale    = "ja_JP"
    }

    # Keep the input menu in the menu bar; it is how the current source is read
    # at a glance when the Karabiner keys switch it.
    "com.apple.TextInputMenu" = {
      visible = true
    }
  }

  settings = {
    enabled_input_sources = {
      domain = "com.apple.HIToolbox"
      key    = "AppleEnabledInputSources"

      value = [
        {
          InputSourceKind       = "Keyboard Layout"
          "KeyboardLayout ID"   = 252
          "KeyboardLayout Name" = "ABC"
        },
        {
          "Bundle ID"     = "com.apple.inputmethod.Kotoeri.RomajiTyping"
          "Input Mode"    = "com.apple.inputmethod.Japanese"
          InputSourceKind = "Input Mode"
        },
        {
          "Bundle ID"     = "com.apple.inputmethod.Kotoeri.RomajiTyping"
          InputSourceKind = "Keyboard Input Method"
        },
        {
          "Bundle ID"     = "com.apple.CharacterPaletteIM"
          InputSourceKind = "Non Keyboard Input Method"
        },
        {
          "Bundle ID"     = "com.apple.50onPaletteIM"
          InputSourceKind = "Non Keyboard Input Method"
        },
        {
          "Bundle ID"     = "com.apple.inputmethod.Korean"
          InputSourceKind = "Keyboard Input Method"
        },
        {
          "Bundle ID"     = "com.apple.inputmethod.Korean"
          "Input Mode"    = "com.apple.inputmethod.Korean.2SetKorean"
          InputSourceKind = "Input Mode"
        },
      ]
    }
  }
}
