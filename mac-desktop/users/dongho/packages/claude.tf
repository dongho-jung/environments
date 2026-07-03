resource "host_package_brew" "claude" {
  name         = "claude"
  package_type = "cask"
}

resource "host_file_block" "claude_aliases" {
  block   = host_file.zshrc.blocks.alias
  content = "alias c='IS_DEMO=1 claude --ide --chrome --allow-dangerously-skip-permissions --effort max --permission-mode bypassPermissions'"
}

resource "host_link" "claude_settings" {
  source      = "${path.module}/claude/settings.json"
  destination = "~/.claude/settings.json"
}
