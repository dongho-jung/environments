resource "host_package_pacman" "neovim" {
  name = "neovim"
}

resource "host_dir" "neovim_data" {
  path = "~/.local/share/nvim"
  mode = "0755"
}

locals {
  neovim_plugins = {
    cmp-buffer = {
      url = "https://github.com/hrsh7th/cmp-buffer.git"
      ref = "b74fab3656eea9de20a9b8116afa3cfc4ec09657"
    }
    cmp-nvim-lsp = {
      url = "https://github.com/hrsh7th/cmp-nvim-lsp.git"
      ref = "cbc7b02bb99fae35cb42f514762b89b5126651ef"
    }
    cmp-path = {
      url = "https://github.com/hrsh7th/cmp-path.git"
      ref = "c642487086dbd9a93160e1679a1327be111cbc25"
    }
    nvim-cmp = {
      url = "https://github.com/hrsh7th/nvim-cmp.git"
      ref = "a1d504892f2bc56c2e79b65c6faded2fd21f3eca"
    }
    nvim-lspconfig = {
      url = "https://github.com/neovim/nvim-lspconfig.git"
      ref = "d224a1920728ba129880efc700d4a0180ac4ecbb"
    }
    vim-solarized = {
      url = "https://github.com/ericbn/vim-solarized.git"
      ref = "034333b1c8b42886e79dd30de458f16172d324ba"
    }
    vim-startify = {
      url = "https://github.com/mhinz/vim-startify.git"
      ref = "4e089dffdad46f3f5593f34362d530e8fe823dcf"
    }
    "which-key.nvim" = {
      url = "https://github.com/folke/which-key.nvim.git"
      ref = "3aab2147e74890957785941f0c1ad87d0a44c15a"
    }
  }
}

resource "host_git_repo" "vim_plug" {
  url  = "https://github.com/junegunn/vim-plug.git"
  path = "${host_dir.neovim_data.path}/vim-plug"
  ref  = "88e31471818e9a29a8a20a0ee61360cfd7bdc1cd"

  delete_on_destroy = false

  depends_on = [
    host_package_pacman.git,
  ]
}

resource "host_git_repo" "neovim_plugins" {
  for_each = local.neovim_plugins

  url  = each.value.url
  path = "${host_dir.neovim_data.path}/plugged/${each.key}"
  ref  = each.value.ref

  delete_on_destroy = false

  depends_on = [
    host_package_pacman.git,
  ]
}

resource "host_link" "neovim_config" {
  source       = "neovim"
  destination  = "~/.config/nvim"
  stage_source = true

  depends_on = [
    host_git_repo.neovim_plugins,
    host_git_repo.vim_plug,
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
