resource "host_package_pacman" "zoxide" {
  name = "zoxide"
}

resource "host_file_block" "zoxide_init" {
  block   = host_file.zshrc.blocks.init
  content = "eval \"$(zoxide init zsh)\""
}
