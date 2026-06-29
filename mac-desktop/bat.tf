resource "host_package_brew" "bat" {
  name = "bat"
}

resource "host_file_block" "bat_aliases" {
  file_block = host_file.zshrc.block["alias"]
  priority   = 50
  content    = "alias cat='bat'"
}
