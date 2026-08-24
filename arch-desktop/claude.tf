# The `claude` CLI is provided by the AUR `claude-code` package, managed through
# host_package_aur (builds via yay/paru). ignore_version defaults to true, so the
# near-daily AUR releases never plan a rebuild; upgrade manually when wanted.
resource "host_package_aur" "claude_code" {
  name = "claude-code"
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
