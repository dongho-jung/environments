resource "host_package_brew" "zoxide" {
  name = "zoxide"
}

resource "host_file_block" "zoxide_init" {
  file_block = host_file.zshrc.block["init"]
  priority   = 20
  content    = "eval \"$(zoxide init zsh)\""
}
