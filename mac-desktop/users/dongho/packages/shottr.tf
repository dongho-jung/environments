resource "host_package_brew" "shottr" {
  name         = "shottr"
  package_type = "cask"
}

resource "host_mac_login_item" "shottr" {
  path = host_package_brew.shottr.app_path
}
