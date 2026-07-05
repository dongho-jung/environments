resource "host_package_brew" "zoxide" {
  name = "zoxide"
}

resource "host_file_block" "zoxide_init" {
  block   = host_file.zshrc.blocks.init
  content = "eval \"$(zoxide init zsh)\""
}
