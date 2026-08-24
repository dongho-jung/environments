resource "host_package_pacman" "git" {
  name = "git"
}

# TUI git client behind the `gg` alias below.
resource "host_package_pacman" "lazygit" {
  name = "lazygit"
}

resource "host_dir" "projects" {
  path = "~/projects"
  mode = "0755"
}

resource "host_git_repo" "environments" {
  url  = "git@github.com:dongho-jung/environments.git"
  path = "${host_dir.projects.path}/environments"

  delete_on_destroy = false

  depends_on = [
    host_package_pacman.git,
    host_ssh_config_host.github,
  ]
}

resource "host_git_repo" "shell_history" {
  url  = "git@github.com:dongho-jung/shell-history.git"
  path = "${host_dir.projects.path}/shell-history"

  delete_on_destroy = false

  depends_on = [
    host_package_pacman.git,
    host_ssh_config_host.github,
  ]
}

resource "host_git_repo" "terraform_provider_host" {
  url  = "git@github.com:dongho-jung/terraform-provider-host.git"
  path = "${host_dir.projects.path}/terraform-provider-host"

  delete_on_destroy = false

  depends_on = [
    host_package_pacman.git,
    host_ssh_config_host.github,
  ]
}

# Repository-local memory for coding agents is intentionally machine-local.
# The harness copies it into temporary worktrees and merges verified updates
# back without ever staging it in repositories we may not own.
resource "host_file" "global_gitignore" {
  path = "~/.config/git/ignore"

  content = <<-EOT
    .ai-metadata
  EOT
}

# GitHub verifies signatures against the signing key registered on the
# account; this file is what lets `git log --show-signature` do the same
# locally.
resource "host_file" "git_allowed_signers" {
  path = "~/.config/git/allowed_signers"

  content = <<-EOT
    dongho971220@gmail.com ${trimspace(host_ssh_key.github.public_key)}
  EOT
}

resource "host_file" "gitconfig" {
  path = "~/.gitconfig"

  content = <<-EOT
    [user]
      email = dongho971220@gmail.com
      name = dongho-jung
      signingkey = ${host_ssh_key.github.path_resolved}.pub
    [gpg]
      format = ssh
    [gpg "ssh"]
      allowedSignersFile = ${host_file.git_allowed_signers.path_resolved}
    [core]
      editor = nvim
      autocrlf = input
      quotePath = false
      excludesFile = ${host_file.global_gitignore.path_resolved}
    [commit]
      verbose = true
      gpgsign = true
    [tag]
      gpgsign = true
    [init]
      defaultBranch = main
    [pull]
      rebase = false
    [push]
      autoSetupRemote = true
  EOT
}

resource "host_file_block" "git_aliases" {
  block = host_file.zshrc.blocks.alias

  content = <<-EOT
    alias ga='git add' gc='git commit -v' gl='git pull' gp='git push' gg='lazygit' gst='git status' gco='git checkout'
    alias gr='git restore' grs='git restore --staged' gd='git diff' gds='git diff --staged' glog='git log --all --decorate --oneline --graph'
  EOT
}

resource "host_schedule" "shell_history_git_auto_commit" {
  schedule          = "*/30 * * * *"
  shell             = "/usr/bin/zsh"
  working_directory = host_git_repo.shell_history.path_resolved

  environment = {
    PATH = "/usr/local/bin:/usr/bin:/bin"
  }

  # crontab + a running cron daemon must exist before this entry can be written.
  depends_on = [
    host_package_pacman.zsh,
    host_systemd_service.cronie,
  ]

  command = <<-EOT
    set -euo pipefail

    branch="main"
    remote="origin"

    # A delayed fetch or push must not overlap the next 30-minute invocation.
    # Keep the lock under .git so it is repository-local and never committed.
    exec 9>".git/terraform-provider-host-shell-history.lock"
    flock -n 9 || exit 0

    git fetch "$remote" "$branch"
    remote_commit="$(git rev-parse FETCH_HEAD)"
    if ! git merge-base --is-ancestor "$remote_commit" HEAD; then
      git pull --rebase --autostash "$remote" "$branch"
    fi

    if [[ -n "$(git status --porcelain)" ]]; then
      git add -A
      git commit -m "Auto update: $(date '+%Y-%m-%d %H:%M:%S')"
      git push "$remote" "$branch"
    fi
  EOT
}
