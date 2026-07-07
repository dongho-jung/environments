locals {
  zsh_dir_path = "~/.zsh"
  zshrc_path   = "~/.zshrc"
}

resource "host_package_pacman" "zsh" {
  name = "zsh"
}

# Wayland clipboard, backs the `y`/`p` aliases below (macOS pbcopy/pbpaste)
resource "host_package_pacman" "wl_clipboard" {
  name = "wl-clipboard"
}

resource "host_dir" "zsh" {
  path = local.zsh_dir_path
  mode = "0755"
}

resource "host_git_repo" "alias_tips" {
  url  = "https://github.com/djui/alias-tips.git"
  path = "${host_dir.zsh.path}/alias-tips"

  delete_on_destroy = false

  depends_on = [
    host_dir.zsh,
  ]
}

resource "host_file" "zshrc" {
  path = local.zshrc_path

  depends_on = [
    host_git_repo.alias_tips,
  ]

  block {
    name    = "environment"
    content = <<-EOT
      export LESSHISTFILE=/dev/null
      export WORDCHARS=""
      export LANG="en_US.UTF-8"
      export LC_ALL="en_US.UTF-8"
      export HISTFILE="${host_git_repo.shell_history.path_resolved}/arch-desktop"
      export HISTSIZE=1000000000
      export SAVEHIST=1000000000
    EOT
  }

  block {
    name = "path"
  }

  block {
    name    = "alias"
    content = <<-EOT
      alias y='wl-copy' p='wl-paste'
      alias rr='source ${local.zshrc_path}'
      alias rm='echo "rm is disabled. use `trash` command instead."'
      alias -g ...='../..'
      alias -g ....='../../..'
    EOT
  }

  block {
    name    = "options"
    content = <<-EOT
      setopt append_history
      setopt autopushd
      setopt extended_glob
      setopt hist_find_no_dups
      setopt hist_ignore_all_dups
      setopt hist_ignore_space
      setopt hist_reduce_blanks
      setopt hist_save_no_dups
      setopt inc_append_history
      setopt interactive_comments
      setopt share_history
    EOT
  }

  block {
    name    = "keybindings"
    content = <<-EOT
      bindkey -e
      bindkey '^[[1;3C' forward-word
      bindkey '^[[1;3D' backward-word
      bindkey '^[[1;5C' end-of-line
      bindkey '^[[1;5D' beginning-of-line
      bindkey '^[b' beginning-of-line
      bindkey '^[f' end-of-line
    EOT
  }

  block {
    name    = "plugins"
    content = "source ${host_git_repo.alias_tips.path}/alias-tips.plugin.zsh"
  }

  block {
    name    = "functions"
    content = <<-EOT
      tmp() {
        TMP=~/tmp/$(date +%F)
        if [ "$#" -gt 0 ]; then
          TMP="$${TMP}-$(echo "$@" | tr ' ' '-')"
        fi
        mkdir -p "$TMP"
        cd "$TMP"
      }
    EOT
  }

  block {
    name = "init"
  }
}
