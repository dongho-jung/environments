resource "host_package_brew" "hiddenbar" {
  name         = "hiddenbar"
  package_type = "cask"
}

resource "host_mac_login_item" "hiddenbar" {
  path = host_package_brew.hiddenbar.app_path
}
