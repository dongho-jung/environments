resource "host_package_brew" "itsycal" {
  name         = "itsycal"
  package_type = "cask"
}

resource "host_mac_login_item" "itsycal" {
  path = "/Applications/Itsycal.app"

  depends_on = [
    host_package_brew.itsycal,
  ]
}
