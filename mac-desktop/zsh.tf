resource "host_package_brew" "zsh" {
  name = "zsh"
}

resource "host_file" "zshrc" {
  path = "~/.zshrc"

  block {
    name    = "environment"
    content = <<-EOT
      export LESSHISTFILE=/dev/null
      export WORDCHARS=""
      export LANG="en_US.UTF-8"
      export LC_ALL="en_US.UTF-8"
      export HISTFILE="$HOME/projects/shell-history/mac-desktop"
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
      alias y='pbcopy' p='pbpaste'
      alias rr='source ~/.zshrc'
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
    content = "source ~/.zsh/alias-tips/alias-tips.plugin.zsh"
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
