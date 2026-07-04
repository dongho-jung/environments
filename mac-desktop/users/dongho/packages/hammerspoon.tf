resource "host_package_brew" "hammerspoon" {
  name         = "hammerspoon"
  package_type = "cask"
}

resource "host_link" "hammerspoon_config" {
  source      = "${path.module}/hammerspoon"
  destination = "~/.hammerspoon"
}

resource "host_mac_login_item" "hammerspoon" {
  path = "/Applications/Hammerspoon.app"

  depends_on = [
    host_package_brew.hammerspoon,
  ]
}
