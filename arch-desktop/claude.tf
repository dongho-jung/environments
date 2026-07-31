# The `claude` CLI is provided by the AUR `claude-code` package, managed through
# host_package_aur (builds via yay/paru). ignore_version defaults to true, so the
# near-daily AUR releases never plan a rebuild; upgrade manually when wanted.
resource "host_package_aur" "claude_code" {
  name = "claude-code"
}

resource "host_file_block" "claude_aliases" {
  block   = host_file.zshrc.blocks.alias
  content = "alias c='IS_DEMO=1 claude --ide --chrome --allow-dangerously-skip-permissions --effort max --permission-mode bypassPermissions'"
}

resource "host_link" "claude_settings" {
  source       = "claude/settings.json"
  destination  = "~/.claude/settings.json"
  stage_source = true
}

resource "host_link" "claude_instructions" {
  source       = "claude/CLAUDE.md"
  destination  = "~/.claude/CLAUDE.md"
  stage_source = true
}

resource "host_link" "claude_command_c" {
  source       = "../common/claude/commands/c.md"
  destination  = "~/.claude/commands/c.md"
  stage_source = true
}

resource "host_link" "claude_command_new_version" {
  source       = "../common/claude/commands/new-version.md"
  destination  = "~/.claude/commands/new-version.md"
  stage_source = true
}
