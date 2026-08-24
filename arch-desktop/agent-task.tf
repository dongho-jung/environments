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

# Keep the familiar one-letter launchers, but make the harness the lifecycle
# owner. Joining all arguments preserves the convenient `o fix this` form as a
# single initial prompt; advanced invocations can call agent-task directly.
resource "host_file_block" "agent_task_functions" {
  block = host_file.zshrc.blocks.functions

  content = <<-EOT
    o() {
      if (( $# )); then
        agent-task start --agent codex "$*"
      else
        agent-task start --agent codex
      fi
    }

    c() {
      if (( $# )); then
        agent-task start --agent claude "$*"
      else
        agent-task start --agent claude
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
