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
    host_link.agent_task_statusline,
  ]
}

# Claude starts this small read-only renderer every second. Keeping it separate
# from the lifecycle CLI avoids reparsing the much larger supervisor on each tick.
resource "host_link" "agent_task_statusline" {
  source       = "agent-task/agent_statusline.py"
  destination  = "${host_dir.local_bin.path}/agent_statusline.py"
  stage_source = true

}

# Ordinary interactive Codex and Claude sessions always use the harness-managed
# lifecycle. Codex can defer its worktree for a clean read-only request. Explicit
# local launches and exact-checkout review commands remain direct because the
# operator or command has selected that checkout deliberately.
resource "host_file_block" "agent_task_functions" {
  block = host_file.zshrc.blocks.functions

  content = <<-EOT
    o() {
      local codex_project="$PWD" codex_arg
      local codex_expect_cd=0
      for codex_arg in "$@"; do
        if (( codex_expect_cd )); then
          codex_project="$codex_arg"
          codex_expect_cd=0
          continue
        fi
        case "$codex_arg" in
          --) break ;;
          -C|--cd) codex_expect_cd=1 ;;
          --cd=*) codex_project="$${codex_arg#--cd=}" ;;
        esac
      done
      if [[ "$codex_project" != /* ]]; then
        codex_project="$PWD/$codex_project"
      fi
      codex_project="$${codex_project:A}"
      local codex_trust="projects={$${(qqq)codex_project}={trust_level=\"trusted\"}}"
      local -a codex_tui=(
        -c "$codex_trust"
        -c 'tui.show_tooltips=false'
        -c 'tui.status_line=["current-dir","thread-title","model-with-reasoning"]'
      )
      if [[ "$${1-}" == "--local" ]]; then
        shift
        command codex "$${codex_tui[@]}" --dangerously-bypass-approvals-and-sandbox "$@"
        return
      fi
      if [[ "$${AI_TASK_HARNESS-}" == "agent-task" ]]; then
        command codex "$${codex_tui[@]}" --dangerously-bypass-approvals-and-sandbox "$@"
        return
      fi
      if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        local codex_has_cd=0
        for codex_arg in "$@"; do
          case "$codex_arg" in
            --) break ;;
            -C|--cd|--cd=*) codex_has_cd=1 ;;
          esac
        done
        if (( codex_has_cd )); then
          agent-task open --quiet --agent codex -- codex "$${codex_tui[@]}" --dangerously-bypass-approvals-and-sandbox "$@"
        else
          command codex "$${codex_tui[@]}" --dangerously-bypass-approvals-and-sandbox "$@"
        fi
        return
      fi
      if [[ "$${1-}" == "resume" ]]; then
        shift
        agent-task resume --quiet --agent codex -- "$@"
        return
      fi
      if [[ "$${1-}" == "--new" ]]; then
        shift
        case "$${1-}" in
          exec|e|review|resume|apply|a|fork|cloud|cloud-tasks|sandbox|--*)
            agent-task open --quiet --new --agent codex -- codex "$${codex_tui[@]}" --dangerously-bypass-approvals-and-sandbox "$@"
            ;;
          -*)
            agent-task open --quiet --new --agent codex -- codex "$${codex_tui[@]}" --dangerously-bypass-approvals-and-sandbox "$@"
            ;;
          *)
            if (( $# )); then
              agent-task open --quiet --new --agent codex "$*"
            else
              agent-task open --quiet --new --agent codex
            fi
            ;;
        esac
        return
      fi
      case "$${1-}" in
        review)
          agent-task open --quiet --require-current --agent codex -- codex "$${codex_tui[@]}" --dangerously-bypass-approvals-and-sandbox "$@"
          return
          ;;
        exec|e|apply|a|fork|cloud|cloud-tasks|sandbox)
          agent-task open --quiet --fresh --agent codex -- codex "$${codex_tui[@]}" --dangerously-bypass-approvals-and-sandbox "$@"
          return
          ;;
        login|logout|mcp|plugin|mcp-server|app-server|remote-control|completion|update|doctor|debug|archive|delete|migrate-rollouts|unarchive|exec-server|features|help|-h|--help|-V|--version)
          command codex "$${codex_tui[@]}" --dangerously-bypass-approvals-and-sandbox "$@"
          return
          ;;
      esac
      if [[ "$${1-}" == -* ]]; then
        agent-task open --quiet --agent codex -- codex "$${codex_tui[@]}" --dangerously-bypass-approvals-and-sandbox "$@"
      elif (( $# )); then
        agent-task open --quiet --agent codex "$*"
      else
        agent-task open --quiet --agent codex
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
            agent-task open --quiet --new --agent claude -- env IS_DEMO=1 claude --ide --chrome --allow-dangerously-skip-permissions --effort max --permission-mode bypassPermissions "$@"
            ;;
          *)
            if (( $# )); then
              agent-task open --quiet --new --agent claude "$*"
            else
              agent-task open --quiet --new --agent claude
            fi
            ;;
        esac
        return
      fi
      case "$${1-}" in
        ultrareview)
          agent-task open --quiet --require-current --agent claude -- env IS_DEMO=1 claude --ide --chrome --allow-dangerously-skip-permissions --effort max --permission-mode bypassPermissions "$@"
          return
          ;;
        auth|auto-mode|doctor|gateway|import|install|mcp|plugin|plugins|project|setup-token|update|upgrade|version|-h|--help|--version)
          command env IS_DEMO=1 claude --ide --chrome --allow-dangerously-skip-permissions --effort max --permission-mode bypassPermissions "$@"
          return
          ;;
      esac
      if [[ "$${1-}" == -* ]]; then
        agent-task open --quiet --agent claude -- env IS_DEMO=1 claude --ide --chrome --allow-dangerously-skip-permissions --effort max --permission-mode bypassPermissions "$@"
      elif (( $# )); then
        agent-task open --quiet --agent claude "$*"
      else
        agent-task open --quiet --agent claude
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
