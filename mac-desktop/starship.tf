resource "host_package_brew" "starship" {
  name = "starship"
}

resource "host_file_block" "starship_init" {
  file_block = host_file.zshrc.block["init"]
  priority   = 10
  content    = "eval \"$(starship init zsh)\""
}
