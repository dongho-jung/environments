resource "host_package_brew" "zsh" {
  name = "zsh"
}

resource "host_file" "zshrc" {
  path   = "~/.zshrc.preview"
  render = "clean"

  block = {
    environment = {
      priority = 10
    }
    path = {
      priority = 20
    }
    alias = {
      priority = 30
    }
    options = {
      priority = 40
      content = trimspace(<<-EOT
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
      )
    }
    keybindings = {
      priority = 50
      content = trimspace(<<-EOT
        bindkey -e
        bindkey '^[[1;3C' forward-word
        bindkey '^[[1;3D' backward-word
        bindkey '^[[1;5C' end-of-line
        bindkey '^[[1;5D' beginning-of-line
        bindkey '^[b' beginning-of-line
        bindkey '^[f' end-of-line
      EOT
      )
    }
    plugins = {
      priority = 60
    }
    functions = {
      priority = 70
      content = trimspace(<<-EOT
        tmp() {
          TMP=~/tmp/$(date +%F)
          if [ "$#" -gt 0 ]; then
            TMP="$${TMP}-$(echo "$@" | tr ' ' '-')"
          fi
          mkdir -p "$TMP"
          cd "$TMP"
        }
      EOT
      )
    }
    init = {
      priority = 80
    }
  }
}

resource "host_file_block" "zsh_environment" {
  file_block = host_file.zshrc.block["environment"]
  priority   = 30
  content = trimspace(<<-EOT
    export LESSHISTFILE=/dev/null
    export WORDCHARS=""
    export LANG="en_US.UTF-8"
    export LC_ALL="en_US.UTF-8"
    export HISTFILE="$HOME/projects/shell-history/mac-desktop"
    export HISTSIZE=1000000000
    export SAVEHIST=1000000000
  EOT
  )
}

resource "host_file_block" "zsh_git_aliases" {
  file_block = host_file.zshrc.block["alias"]
  priority   = 30
  content    = "alias ga='git add' gc='git commit -v' gl='git pull' gp='git push' gg='lazygit' gst='git status' gco='git checkout'"
}

resource "host_file_block" "zsh_git_more_aliases" {
  file_block = host_file.zshrc.block["alias"]
  priority   = 31
  content    = "alias gr='git restore' grs='git restore --staged' gd='git diff' gds='git diff --staged' glog='git log --all --decorate --oneline --graph'"
}

resource "host_file_block" "zsh_clipboard_aliases" {
  file_block = host_file.zshrc.block["alias"]
  priority   = 70
  content    = "alias y='pbcopy' p='pbpaste'"
}

resource "host_file_block" "zsh_misc_aliases" {
  file_block = host_file.zshrc.block["alias"]
  priority   = 80
  content = trimspace(<<-EOT
    alias rr='source ~/.zshrc'
    alias rm='echo "rm is disabled. use `trash` command instead."'
  EOT
  )
}

resource "host_file_block" "zsh_global_aliases" {
  file_block = host_file.zshrc.block["alias"]
  priority   = 90
  content = trimspace(<<-EOT
    alias -g ...='../..'
    alias -g ....='../../..'
  EOT
  )
}

resource "host_file_block" "alias_tips" {
  file_block = host_file.zshrc.block["plugins"]
  priority   = 20
  content    = "source ~/.zsh/alias-tips/alias-tips.plugin.zsh"
}
