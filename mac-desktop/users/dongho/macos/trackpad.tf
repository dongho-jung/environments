resource "host_macos_default" "trackpad_tap_to_click" {
  domain = "com.apple.AppleMultitouchTrackpad"
  key    = "Clicking"
  bool   = true
}

resource "host_macos_default" "trackpad_three_finger_drag" {
  domain = "com.apple.AppleMultitouchTrackpad"
  key    = "TrackpadThreeFingerDrag"
  bool   = false
}

resource "host_macos_default" "trackpad_right_click" {
  domain = "com.apple.AppleMultitouchTrackpad"
  key    = "TrackpadRightClick"
  bool   = true
}

resource "host_macos_default" "trackpad_force_click" {
  domain = "NSGlobalDomain"
  key    = "com.apple.trackpad.forceClick"
  bool   = true
}

resource "host_macos_default" "bluetooth_trackpad_tap_to_click" {
  domain = "com.apple.driver.AppleBluetoothMultitouch.trackpad"
  key    = "Clicking"
  bool   = true
}

resource "host_macos_default" "bluetooth_trackpad_three_finger_drag" {
  domain = "com.apple.driver.AppleBluetoothMultitouch.trackpad"
  key    = "TrackpadThreeFingerDrag"
  bool   = false
}

resource "host_macos_default" "bluetooth_trackpad_right_click" {
  domain = "com.apple.driver.AppleBluetoothMultitouch.trackpad"
  key    = "TrackpadRightClick"
  bool   = true
}
