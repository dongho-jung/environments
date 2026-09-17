locals {
  zsh_dir_path = "~/.zsh"
  zshrc_path   = "~/.zshrc"
}

resource "host_package_pacman" "zsh" {
  name = "zsh"
}

resource "host_package_pacman" "zsh_completions" {
  name = "zsh-completions"
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
  ref  = "41cb143ccc3b8cc444bf20257276cb43275f65c4"

  delete_on_destroy = false

  depends_on = [
    host_dir.zsh,
    host_package_pacman.git,
  ]
}

resource "host_file" "zshrc" {
  path = local.zshrc_path

  depends_on = [
    host_git_repo.alias_tips,
    host_package_pacman.zsh_completions,
  ]

  block {
    name    = "environment"
    content = <<-EOT
      export LESSHISTFILE=/dev/null
      export WORDCHARS=""
      export LANG="en_US.UTF-8"
      export LC_ALL="en_US.UTF-8"
      export KUBECONFIG=~/.kube/vultr-stg.yaml
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
      alias k='kubectl'
      alias y='wl-copy' p='wl-paste'
      alias rr='source ${local.zshrc_path}'
      alias rm='echo "rm is disabled. use \`trash\` command instead."'
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

      # Open the current command line in $EDITOR (nvim) and run what comes back.
      # Bash binds ^X^E out of the box; zsh leaves it undefined and needs the
      # widget autoloaded and registered with zle first.
      autoload -Uz edit-command-line
      zle -N edit-command-line
      bindkey '^X^E' edit-command-line
    EOT
  }

  block {
    name    = "completion"
    content = <<-EOT
      # Enable the completion system. This is what makes `git <tab>` (subcommands)
      # and `git checkout <tab>` (branches) work; `_git` autoloads lazily on first
      # use. Placed before the plugins block so fzf sees the modern completion
      # system (compdef) already active instead of falling back to compctl.
      autoload -Uz compinit
      # Full rebuild (fpath scan + security audit, ~0.3s) at most once a day; every
      # other shell fast-loads the cached ~/.zcompdump with the checks skipped (~7ms).
      () {
        if (( $# )); then
          compinit
        else
          compinit -C
        fi
      } ~/.zcompdump(#qN.mh+24)
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

      # API keys live in ~/.key, which is deliberately unmanaged: it never
      # enters this repository, Terraform state or Git. `sk` loads it on demand
      # instead of every shell paying for it. local_options keeps allexport
      # scoped to this function, so the file's bare NAME=value lines reach child
      # processes without turning the whole shell into an exporting one.
      sk() {
        if [[ ! -r ~/.key ]]; then
          print -u2 "sk: ~/.key not found"
          return 1
        fi
        setopt local_options allexport
        source ~/.key
      }
    EOT
  }

  block {
    name = "init"
  }
}
