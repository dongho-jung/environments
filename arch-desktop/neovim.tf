resource "host_package_pacman" "neovim" {
  name = "neovim"
}

resource "host_dir" "neovim_data" {
  path = "~/.local/share/nvim"
  mode = "0755"
}

resource "host_git_repo" "vim_plug" {
  url  = "https://github.com/junegunn/vim-plug.git"
  path = "${host_dir.neovim_data.path}/vim-plug"

  delete_on_destroy = false

  depends_on = [
    host_package_pacman.git,
  ]
}

resource "host_link" "neovim_config" {
  source      = "neovim"
  destination = "~/.config/nvim"

  depends_on = [
    host_package_pacman.neovim,
  ]
}

resource "host_file_block" "neovim_environment" {
  block   = host_file.zshrc.blocks.environment
  content = "export EDITOR=nvim"
}

resource "host_file_block" "neovim_aliases" {
  block   = host_file.zshrc.blocks.alias
  content = "alias vi=\"nvim\" vim=\"vi\""
}
