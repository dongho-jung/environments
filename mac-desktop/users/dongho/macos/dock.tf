resource "host_macos_dock" "default" {
  apps = [
    "/System/Applications/System Settings.app",
    "/Applications/Google Chrome.app",
  ]

  folders = [
    "/Users/dongho/Downloads",
  ]
}

resource "host_macos_default" "dock_autohide" {
  domain = "com.apple.dock"
  key    = "autohide"
  bool   = true
}

resource "host_macos_default" "dock_show_recents" {
  domain = "com.apple.dock"
  key    = "show-recents"
  bool   = false
}

resource "host_macos_default" "dock_minimize_to_application" {
  domain = "com.apple.dock"
  key    = "minimize-to-application"
  bool   = false
}

resource "host_macos_default" "dock_show_process_indicators" {
  domain = "com.apple.dock"
  key    = "show-process-indicators"
  bool   = true
}

resource "host_macos_default" "dock_bottom_right_hot_corner" {
  domain = "com.apple.dock"
  key    = "wvous-br-corner"
  int    = 14
}
