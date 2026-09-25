# System Settings writes every trackpad preference to three places at once: the
# built-in trackpad domain, the Bluetooth trackpad domain, and a host-specific
# global key that the Trackpad pane reads back. Writing only one of them leaves
# the pane showing a value the driver does not use, so each gesture is declared
# once here and applied to all three.
#
# macOS stores these with a fixed native type per key, and the trackpad daemon
# rewrites a value that arrives with the wrong one. `value` is the type the two
# trackpad domains store and `host_value` the type the host-specific key
# stores; they differ for tap to click, pinch, and rotate.
locals {
  trackpad_gestures = {
    # Tap to click.
    Clicking = {
      value      = true
      host_key   = "com.apple.mouse.tapBehavior"
      host_value = 1
    }
    # Secondary click with two fingers.
    TrackpadRightClick = {
      value      = true
      host_key   = "com.apple.trackpad.enableSecondaryClick"
      host_value = true
    }
    TrackpadThreeFingerDrag = {
      value      = false
      host_key   = "com.apple.trackpad.threeFingerDragGesture"
      host_value = false
    }
    # Look up is bound to Force Click, not to a three-finger tap.
    TrackpadThreeFingerTapGesture = {
      value      = 0
      host_key   = "com.apple.trackpad.threeFingerTapGesture"
      host_value = 0
    }
    # Swipe between full-screen apps and pages.
    TrackpadThreeFingerHorizSwipeGesture = {
      value      = 2
      host_key   = "com.apple.trackpad.threeFingerHorizSwipeGesture"
      host_value = 2
    }
    TrackpadThreeFingerVertSwipeGesture = {
      value      = 2
      host_key   = "com.apple.trackpad.threeFingerVertSwipeGesture"
      host_value = 2
    }
    TrackpadFourFingerHorizSwipeGesture = {
      value      = 2
      host_key   = "com.apple.trackpad.fourFingerHorizSwipeGesture"
      host_value = 2
    }
    # Mission Control with four fingers up, App Exposé with four fingers down.
    TrackpadFourFingerVertSwipeGesture = {
      value      = 2
      host_key   = "com.apple.trackpad.fourFingerVertSwipeGesture"
      host_value = 2
    }
    # Launchpad and Show Desktop.
    TrackpadFourFingerPinchGesture = {
      value      = 2
      host_key   = "com.apple.trackpad.fourFingerPinchSwipeGesture"
      host_value = 2
    }
    TrackpadFiveFingerPinchGesture = {
      value      = 2
      host_key   = "com.apple.trackpad.fiveFingerPinchSwipeGesture"
      host_value = 2
    }
    # Notification Centre from the right edge.
    TrackpadTwoFingerFromRightEdgeSwipeGesture = {
      value      = 3
      host_key   = "com.apple.trackpad.twoFingerFromRightEdgeSwipeGesture"
      host_value = 3
    }
    # Smart zoom on a two-finger double tap.
    TrackpadTwoFingerDoubleTapGesture = {
      value      = 1
      host_key   = "com.apple.trackpad.twoFingerDoubleTapGesture"
      host_value = 1
    }
    TrackpadPinch = {
      value      = 1
      host_key   = "com.apple.trackpad.pinchGesture"
      host_value = true
    }
    TrackpadRotate = {
      value      = 1
      host_key   = "com.apple.trackpad.rotateGesture"
      host_value = true
    }
    TrackpadMomentumScroll = {
      value      = true
      host_key   = "com.apple.trackpad.momentumScroll"
      host_value = true
    }
  }
}

resource "host_mac_settings" "trackpad" {
  groups = {
    "com.apple.AppleMultitouchTrackpad" = {
      for name, gesture in local.trackpad_gestures : name => gesture.value
    }

    "com.apple.driver.AppleBluetoothMultitouch.trackpad" = {
      for name, gesture in local.trackpad_gestures : name => gesture.value
    }

    NSGlobalDomain = {
      "com.apple.trackpad.forceClick"  = true
      "com.apple.swipescrolldirection" = true
    }
  }

  # The Trackpad pane keeps its own copy of every gesture per host.
  settings = {
    for name, gesture in local.trackpad_gestures : "host_${name}" => {
      domain       = "NSGlobalDomain"
      key          = gesture.host_key
      current_host = true
      value        = gesture.host_value
    }
  }
}
