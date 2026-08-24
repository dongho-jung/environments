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

# Codex reserves the current checkout with an ignored .ai-lock. The first
# session works in place; concurrent sessions fall back to isolated managed
# worktrees. Administration commands stay direct, and Claude keeps its existing
# opt-in behavior.
resource "host_file_block" "agent_task_functions" {
  block = host_file.zshrc.blocks.functions

  content = <<-EOT
    o() {
      if [[ "$${1-}" == "--local" ]]; then
        shift
        command codex --dangerously-bypass-approvals-and-sandbox "$@"
        return
      fi
      if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1 || [[ "$${AI_TASK_HARNESS-}" == "agent-task" ]]; then
        command codex --dangerously-bypass-approvals-and-sandbox "$@"
        return
      fi
      if [[ "$${1-}" == "resume" ]]; then
        shift
        agent-task resume --agent codex "$@"
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
      if [[ "$${1-}" == "--new" ]]; then
        shift
        if [[ "$${1-}" == -* ]]; then
          agent-task start --agent codex -- codex --dangerously-bypass-approvals-and-sandbox "$@"
        elif (( $# )); then
          agent-task open --managed --new --agent codex "$*"
        else
          agent-task open --managed --new --agent codex
        fi
        return
      fi
      case "$${1-}" in
        exec|e|review|login|logout|mcp|plugin|mcp-server|app-server|remote-control|completion|update|doctor|sandbox|debug|apply|a|archive|delete|migrate-rollouts|unarchive|fork|cloud|exec-server|features|help|-h|--help|-V|--version)
          command codex --dangerously-bypass-approvals-and-sandbox "$@"
          return
          ;;
      esac
      if [[ "$${1-}" == -* ]]; then
        agent-task open --auto --agent codex -- codex --dangerously-bypass-approvals-and-sandbox "$@"
      elif (( $# )); then
        agent-task open --auto --agent codex "$*"
      else
        agent-task open --auto --agent codex
      fi
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
