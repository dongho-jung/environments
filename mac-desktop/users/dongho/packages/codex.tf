resource "host_package_brew" "codex" {
  name         = "codex"
  package_type = "cask"
}

resource "host_file_block" "codex_aliases" {
  block   = host_file.zshrc.blocks.alias
  content = "alias o='codex --dangerously-bypass-approvals-and-sandbox'"
}

resource "host_link" "codex_keybindings" {
  source      = "${path.module}/codex/keybindings.json"
  destination = "~/.codex/keybindings.json"
}

resource "host_link" "codex_default_rules" {
  source      = "${path.module}/codex/rules/default.rules"
  destination = "~/.codex/rules/default.rules"
}

resource "host_link" "codex_command_c" {
  source      = "${path.module}/codex/commands/c.md"
  destination = "~/.codex/commands/c.md"
}
