resource "host_macos_default" "keyboard_fn_state" {
  domain = "NSGlobalDomain"
  key    = "com.apple.keyboard.fnState"
  bool   = true
}

resource "host_macos_default" "keyboard_automatic_capitalization" {
  domain = "NSGlobalDomain"
  key    = "NSAutomaticCapitalizationEnabled"
  bool   = true
}

resource "host_macos_default" "keyboard_automatic_period_substitution" {
  domain = "NSGlobalDomain"
  key    = "NSAutomaticPeriodSubstitutionEnabled"
  bool   = true
}

resource "host_macos_default" "window_drag_on_gesture" {
  domain = "NSGlobalDomain"
  key    = "NSWindowShouldDragOnGesture"
  bool   = true
}

resource "host_macos_default" "window_miniaturize_on_double_click" {
  domain = "NSGlobalDomain"
  key    = "AppleMiniaturizeOnDoubleClick"
  bool   = false
}
