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

# The Codex App Server notification bridge uses its supported WebSocket RPC
# endpoint to steer an active turn or start a new turn in an idle TUI.
resource "host_package_pacman" "python_websockets" {
  name = "python-websockets"
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
    host_package_pacman.python_websockets,
  ]
}

# Interactive Codex and Claude tasks follow settings.agent_task_mode in each
# repository's ignored .ai-memory. "worktree" always isolates tasks, while
# "current" reserves and edits the current checkout without a task branch.
# Repositories without a recorded choice retain contention-aware compatibility
# behavior until an agent verifies and records the durable policy.
resource "host_file_block" "agent_task_functions" {
  block = host_file.zshrc.blocks.functions

  content = <<-EOT
    o() {
      if [[ "$${1-}" == "--local" ]]; then
        shift
        command codex --dangerously-bypass-approvals-and-sandbox "$@"
        return
      fi
      if [[ "$${AI_TASK_HARNESS-}" == "agent-task" ]]; then
        command codex --dangerously-bypass-approvals-and-sandbox "$@"
        return
      fi
      if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        local codex_arg codex_has_cd=0
        for codex_arg in "$@"; do
          case "$codex_arg" in
            --) break ;;
            -C|--cd|--cd=*) codex_has_cd=1 ;;
          esac
        done
        if (( codex_has_cd )); then
          agent-task open --auto --agent codex -- codex --dangerously-bypass-approvals-and-sandbox "$@"
        else
          command codex --dangerously-bypass-approvals-and-sandbox "$@"
        fi
        return
      fi
      if [[ "$${1-}" == "resume" ]]; then
        shift
        agent-task resume --agent codex -- "$@"
        return
      fi
      if [[ "$${1-}" == "--task" ]]; then
        shift
        if (( $# )); then
          agent-task open --auto --agent codex "$*"
        else
          agent-task open --auto --agent codex
        fi
        return
      fi
      if [[ "$${1-}" == "--new" ]]; then
        shift
        case "$${1-}" in
          exec|e|review|resume|apply|a|fork|cloud|cloud-tasks|sandbox|--*)
            agent-task open --managed --new --agent codex -- codex --dangerously-bypass-approvals-and-sandbox "$@"
            ;;
          -*)
            agent-task open --managed --new --agent codex -- codex --dangerously-bypass-approvals-and-sandbox "$@"
            ;;
          *)
            if (( $# )); then
              agent-task open --managed --new --agent codex "$*"
            else
              agent-task open --managed --new --agent codex
            fi
            ;;
        esac
        return
      fi
      case "$${1-}" in
        review)
          agent-task open --auto --require-current --agent codex -- codex --dangerously-bypass-approvals-and-sandbox "$@"
          return
          ;;
        exec|e|apply|a|fork|cloud|cloud-tasks|sandbox)
          agent-task open --auto --fresh --agent codex -- codex --dangerously-bypass-approvals-and-sandbox "$@"
          return
          ;;
        login|logout|mcp|plugin|mcp-server|app-server|remote-control|completion|update|doctor|debug|archive|delete|migrate-rollouts|unarchive|exec-server|features|help|-h|--help|-V|--version)
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
      if [[ "$${1-}" == "--local" ]]; then
        shift
        command env IS_DEMO=1 claude --ide --chrome --allow-dangerously-skip-permissions --effort max --permission-mode bypassPermissions "$@"
        return
      fi
      case "$${1-}" in
        agents|attach|logs|stop|rm)
          command env IS_DEMO=1 claude --ide --chrome --allow-dangerously-skip-permissions --effort max --permission-mode bypassPermissions "$@"
          return
          ;;
      esac
      local claude_arg claude_owns_lifecycle=0
      for claude_arg in "$@"; do
        case "$claude_arg" in
          --)
            break
            ;;
          --background|--background=*|--bg|--bg=*|--tmux|--tmux=*|--worktree|--worktree=*|-w)
            claude_owns_lifecycle=1
            ;;
        esac
      done
      if (( claude_owns_lifecycle )); then
        if [[ "$${1-}" == "--new" ]]; then
          shift
        elif [[ "$${1-}" == "--task" ]]; then
          print -u2 "c: --task cannot be combined with Claude-managed background or worktree modes"
          return 2
        fi
        command env IS_DEMO=1 claude --ide --chrome --allow-dangerously-skip-permissions --effort max --permission-mode bypassPermissions "$@"
        return
      fi
      if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1 || [[ "$${AI_TASK_HARNESS-}" == "agent-task" ]]; then
        command env IS_DEMO=1 claude --ide --chrome --allow-dangerously-skip-permissions --effort max --permission-mode bypassPermissions "$@"
        return
      fi
      if [[ "$${1-}" == "--new" ]]; then
        shift
        case "$${1-}" in
          ultrareview|--*|-*)
            agent-task open --managed --new --agent claude -- env IS_DEMO=1 claude --ide --chrome --allow-dangerously-skip-permissions --effort max --permission-mode bypassPermissions "$@"
            ;;
          *)
            if (( $# )); then
              agent-task open --managed --new --agent claude "$*"
            else
              agent-task open --managed --new --agent claude
            fi
            ;;
        esac
        return
      fi
      if [[ "$${1-}" == "--task" ]]; then
        shift
        if (( $# )); then
          agent-task open --auto --agent claude "$*"
        else
          agent-task open --auto --agent claude
        fi
        return
      fi
      case "$${1-}" in
        ultrareview)
          agent-task open --auto --require-current --agent claude -- env IS_DEMO=1 claude --ide --chrome --allow-dangerously-skip-permissions --effort max --permission-mode bypassPermissions "$@"
          return
          ;;
        auth|auto-mode|doctor|gateway|import|install|mcp|plugin|plugins|project|setup-token|update|upgrade|version|-h|--help|--version)
          command env IS_DEMO=1 claude --ide --chrome --allow-dangerously-skip-permissions --effort max --permission-mode bypassPermissions "$@"
          return
          ;;
      esac
      if [[ "$${1-}" == -* ]]; then
        agent-task open --auto --agent claude -- env IS_DEMO=1 claude --ide --chrome --allow-dangerously-skip-permissions --effort max --permission-mode bypassPermissions "$@"
      elif (( $# )); then
        agent-task open --auto --agent claude "$*"
      else
        agent-task open --auto --agent claude
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
