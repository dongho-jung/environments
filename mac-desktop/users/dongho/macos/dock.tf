resource "host_macos_dock" "default" {
  apps = [
    "/System/Applications/System Settings.app",
    "/Applications/Google Chrome.app",
  ]

  folders = [
    "/Users/dongho/Downloads",
  ]
}
