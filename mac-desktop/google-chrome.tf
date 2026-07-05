resource "host_package_brew" "google_chrome" {
  name         = "google-chrome"
  package_type = "cask"
}

resource "host_mac_dock_app" "google_chrome" {
  path     = host_package_brew.google_chrome.app_path
  priority = 20
}
