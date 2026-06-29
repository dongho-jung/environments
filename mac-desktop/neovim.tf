resource "host_package_brew" "neovim" {
  name = "neovim"
}

resource "host_file_block" "neovim_environment" {
  file_block = host_file.zshrc.block["environment"]
  priority   = 10
  content    = "export EDITOR=nvim"
}

resource "host_file_block" "neovim_aliases" {
  file_block = host_file.zshrc.block["alias"]
  priority   = 60
  content    = "alias vi=\"nvim\" vim=\"vi\""
}
