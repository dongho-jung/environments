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

resource "host_dir" "codex_agents_plugins" {
  path = "~/.agents/plugins"
  mode = "0755"
}

resource "host_dir" "codex_personal_plugins" {
  path = "~/plugins"
  mode = "0755"
}

resource "host_link" "codex_plugins_marketplace" {
  source       = "../common/codex/.agents/plugins/marketplace.json"
  destination  = "~/.agents/plugins/marketplace.json"
  stage_source = true

  depends_on = [
    host_dir.codex_agents_plugins,
  ]
}

resource "host_link" "codex_smart_commit_plugin" {
  source       = "../common/codex/plugins/smart-commit"
  destination  = "~/plugins/smart-commit"
  stage_source = true

  depends_on = [
    host_dir.codex_personal_plugins,
  ]
}
