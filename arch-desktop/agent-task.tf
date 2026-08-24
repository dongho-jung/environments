# Coding agents run inside an externally enforced disposable-worktree sandbox.
resource "host_package_pacman" "bubblewrap" {
  name = "bubblewrap"
}

resource "host_dir" "local_bin" {
  path = "~/.local/bin"
  mode = "0755"
}

resource "host_file_block" "local_bin_path" {
  block   = host_file.zshrc.blocks.path
  content = "export PATH=\"$HOME/.local/bin:$PATH\""
}

resource "host_link" "agent_task" {
  source       = "agent-task/agent_task.py"
  destination  = "${host_dir.local_bin.path}/agent-task"
  stage_source = true

  depends_on = [
    host_package_pacman.bubblewrap,
    host_package_pacman.git,
  ]
}

# Keep the familiar one-letter launchers. In a Git repository they reopen the
# interrupted task for that agent or create a new managed task. Outside Git, and
# for explicit CLI flags, they preserve the original direct-launch behavior.
resource "host_file_block" "agent_task_functions" {
  block = host_file.zshrc.blocks.functions

  content = <<-EOT
    o() {
      if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1 || [[ "$${1-}" == -* && "$${1-}" != "--new" ]]; then
        command codex --dangerously-bypass-approvals-and-sandbox "$@"
        return
      fi
      if [[ "$${1-}" == "--new" ]]; then
        shift
        if (( $# )); then
          agent-task open --new --agent codex "$*"
        else
          agent-task open --new --agent codex
        fi
        return
      fi
      if (( $# )); then
        agent-task open --agent codex "$*"
      else
        agent-task open --agent codex
      fi
    }

    c() {
      if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1 || [[ "$${1-}" == -* && "$${1-}" != "--new" ]]; then
        command env IS_DEMO=1 claude --ide --chrome --allow-dangerously-skip-permissions --effort max --permission-mode bypassPermissions "$@"
        return
      fi
      if [[ "$${1-}" == "--new" ]]; then
        shift
        if (( $# )); then
          agent-task open --new --agent claude "$*"
        else
          agent-task open --new --agent claude
        fi
        return
      fi
      if (( $# )); then
        agent-task open --agent claude "$*"
      else
        agent-task open --agent claude
      fi
    }
  EOT
}

# A crashed parent process cannot perform its final integration or cleanup.
# Reconcile from a separate process so every managed task eventually reaches a
# terminal or recovery state without relying on the coding agent's behavior.
resource "host_schedule" "agent_task_reconcile" {
  schedule          = "17 * * * *"
  shell             = "/usr/bin/zsh"
  working_directory = host_dir.projects.path_resolved

  environment = {
    PATH = "${host_dir.local_bin.path_resolved}:/usr/local/bin:/usr/bin:/bin"
  }

  command = "agent-task reconcile --quiet"

  depends_on = [
    host_link.agent_task,
    host_systemd_service.cronie,
  ]
}
