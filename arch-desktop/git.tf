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

# Public repositories clone over HTTPS so a fresh host needs no registered SSH
# key before the first apply. Pushing uses the gh credential helper configured
# in .gitconfig below.
resource "host_git_repo" "environments" {
  url  = "https://github.com/dongho-jung/environments.git"
  path = "${host_dir.projects.path}/environments"

  delete_on_destroy = false

  depends_on = [
    host_package_pacman.git,
  ]
}

# The only private repository, so this is the one clone that needs the SSH key
# registered with the GitHub account first.
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
  url  = "https://github.com/dongho-jung/terraform-provider-host.git"
  path = "${host_dir.projects.path}/terraform-provider-host"

  delete_on_destroy = false

  depends_on = [
    host_package_pacman.git,
  ]
}

resource "host_file" "gitconfig" {
  path = "~/.gitconfig"

  content = <<-EOT
    [user]
      email = dongho971220@gmail.com
      name = dongho-jung
    [core]
      editor = nvim
      autocrlf = input
      quotePath = false
    [commit]
      verbose = true
    [init]
      defaultBranch = main
    [pull]
      rebase = false
    [push]
      autoSetupRemote = true
    [credential "https://github.com"]
      helper = !/usr/bin/gh auth git-credential
  EOT

  depends_on = [
    host_package_pacman.gh,
  ]
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
