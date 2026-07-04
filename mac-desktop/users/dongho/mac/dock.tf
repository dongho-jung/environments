data "host_package_brew" "google_chrome" {
  name         = "google-chrome"
  package_type = "cask"
}

resource "host_mac_dock" "default" {
  apps = [
    "/System/Applications/System Settings.app",
    data.host_package_brew.google_chrome.app_path,
  ]

  folders = [
    "~/Downloads",
  ]
}
