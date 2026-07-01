resource "host_package_brew" "starship" {
  name = "starship"
}

resource "host_file_block" "starship_init" {
  block   = host_file.zshrc.blocks.init
  content = "eval \"$(starship init zsh)\""
}
