resource "host_package_pacman" "bat" {
  name = "bat"
}

resource "host_file_block" "bat_aliases" {
  block   = host_file.zshrc.blocks.alias
  content = "alias cat='bat'"
}
