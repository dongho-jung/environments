# The `codex` CLI is provided by the official `openai-codex` package (extra repo).
resource "host_package_pacman" "codex" {
  name = "openai-codex"
}

resource "host_file_block" "codex_aliases" {
  block   = host_file.zshrc.blocks.alias
  content = "alias o='codex --dangerously-bypass-approvals-and-sandbox'"
}

resource "host_link" "codex_keybindings" {
  source       = "codex/keybindings.json"
  destination  = "~/.codex/keybindings.json"
  stage_source = true
}

resource "host_link" "codex_default_rules" {
  source       = "codex/rules/default.rules"
  destination  = "~/.codex/rules/default.rules"
  stage_source = true
}

resource "host_link" "codex_agents" {
  source       = "codex/AGENTS.md"
  destination  = "~/.codex/AGENTS.md"
  stage_source = true
}
