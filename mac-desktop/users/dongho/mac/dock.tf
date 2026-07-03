resource "host_mac_dock" "default" {
  apps = [
    "/System/Applications/System Settings.app",
    "/Applications/Google Chrome.app",
  ]

  folders = [
    pathexpand("~/Downloads"),
  ]
}
