resource "host_package_brew" "karabiner_elements" {
  name         = "karabiner-elements"
  package_type = "cask"
}

resource "host_file" "karabiner_config" {
  path    = "~/.config/karabiner/karabiner.json"
  content = file("${path.module}/karabiner/karabiner.json")

  depends_on = [host_package_brew.karabiner_elements]
}
