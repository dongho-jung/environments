resource "host_package_brew" "bat" {
  name = "bat"
}

resource "host_file_block" "bat_aliases" {
  block   = host_file.zshrc.blocks.alias
  content = "alias cat='bat'"
}
