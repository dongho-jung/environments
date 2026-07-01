resource "host_schedule" "shell_history_git_auto_commit" {
  schedule = "*/30 * * * *"
  shell    = "/bin/zsh"

  command = <<-EOT
    set -euo pipefail

    cd ~/projects/shell-history || exit 1
    export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

    branch="main"
    remote="origin"

    git fetch "$remote" "$branch"
    if ! git diff --quiet "HEAD..$remote/$branch"; then
      git pull --rebase --autostash "$remote" "$branch"
    fi

    if [[ -n "$(git status --porcelain)" ]]; then
      git add -A
      git commit -m "Auto update: $(date '+%Y-%m-%d %H:%M:%S')"
      git push "$remote" "$branch"
    fi
  EOT
}
