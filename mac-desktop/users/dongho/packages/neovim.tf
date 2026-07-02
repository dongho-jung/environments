resource "host_package_brew" "neovim" {
  name = "neovim"
}

resource "host_link" "neovim_config" {
  source      = "${path.module}/neovim"
  destination = "~/.config/nvim"
}

resource "host_file_block" "neovim_environment" {
  block   = host_file.zshrc.blocks.environment
  content = "export EDITOR=nvim"
}

resource "host_file_block" "neovim_aliases" {
  block   = host_file.zshrc.blocks.alias
  content = "alias vi=\"nvim\" vim=\"vi\""
}
