resource "host_package_brew" "hammerspoon" {
  name         = "hammerspoon"
  package_type = "cask"
}

resource "host_link" "hammerspoon_config" {
  source      = "${path.module}/hammerspoon"
  destination = "~/.hammerspoon"
}
