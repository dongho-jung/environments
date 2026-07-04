resource "host_package_brew" "itsycal" {
  name         = "itsycal"
  package_type = "cask"
}

resource "host_mac_login_item" "itsycal" {
  path = host_package_brew.itsycal.app_path
}
