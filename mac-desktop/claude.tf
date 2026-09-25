resource "host_package_brew" "claude" {
  name         = "claude"
  package_type = "cask"
}

# Claude Code only asserts caffeinate -i -t 300 per request, so a turn longer
# than five minutes lets the idle sleep timer suspend the session mid-response.
# caffeinate -is holds the assertion for the whole session; the display still sleeps.
resource "host_file_block" "claude_aliases" {
  block   = host_file.zshrc.blocks.alias
  content = "alias c='IS_DEMO=1 caffeinate -is claude --ide --chrome --allow-dangerously-skip-permissions --effort max --permission-mode bypassPermissions'"
}

resource "host_link" "claude_settings" {
  source      = "claude/settings.json"
  destination = "~/.claude/settings.json"
}

resource "host_link" "claude_instructions" {
  source      = "../arch-desktop/claude/CLAUDE.md"
  destination = "~/.claude/CLAUDE.md"
}
