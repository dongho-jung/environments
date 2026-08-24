# Bubblewrap is no longer owned by agent-task, but it remains installed as a
# dependency of other desktop packages. Forget the old resource without asking
# Pacman to remove the shared package.
removed {
  from = host_package_pacman.bubblewrap

  lifecycle {
    destroy = false
  }
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
    host_package_pacman.git,
  ]
}

# Keep ordinary sessions identical to the native CLIs. Managed worktrees are an
# explicit parallel-work option: --new starts one and --task resumes or creates
# one through the harness.
resource "host_file_block" "agent_task_functions" {
  block = host_file.zshrc.blocks.functions

  content = <<-EOT
    o() {
      if [[ "$${1-}" == "--new" ]]; then
        shift
        if (( $# )); then
          agent-task open --managed --new --agent codex "$*"
        else
          agent-task open --managed --new --agent codex
        fi
        return
      fi
      if [[ "$${1-}" == "--task" ]]; then
        shift
        if (( $# )); then
          agent-task open --managed --agent codex "$*"
        else
          agent-task open --managed --agent codex
        fi
        return
      fi
      command codex --dangerously-bypass-approvals-and-sandbox "$@"
    }

    c() {
      if [[ "$${1-}" == "--new" ]]; then
        shift
        if (( $# )); then
          agent-task open --managed --new --agent claude "$*"
        else
          agent-task open --managed --new --agent claude
        fi
        return
      fi
      if [[ "$${1-}" == "--task" ]]; then
        shift
        if (( $# )); then
          agent-task open --managed --agent claude "$*"
        else
          agent-task open --managed --agent claude
        fi
        return
      fi
      command env IS_DEMO=1 claude --ide --chrome --allow-dangerously-skip-permissions --effort max --permission-mode bypassPermissions "$@"
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
