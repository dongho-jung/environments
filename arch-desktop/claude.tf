# The `claude` CLI is provided by the AUR `claude-code` package, managed through
# host_package_aur (builds via yay/paru). ignore_version defaults to true, so the
# near-daily AUR releases never plan a rebuild; upgrade manually when wanted.
resource "host_package_aur" "claude_code" {
  name = "claude-code"
}

# Claude Code rewrites this file itself whenever a setting changes in a session
# (/model, scroll speed, ...), and its atomic write resolves one level of the
# symbolic link and replaces the provider's staged `current` link with a regular
# file. The staged host_link therefore broke on the first such write
# (2026-09-21) and failed every later apply, so Terraform installs a copy
# instead and the repository file stays the source of truth: a setting changed
# in a session shows up as a content diff here and is reverted on apply. Same
# fix as mac-desktop/claude.tf.
resource "host_file" "claude_settings" {
  path    = "~/.claude/settings.json"
  content = file("${path.module}/claude/settings.json")
}

resource "host_link" "claude_instructions" {
  source       = "claude/CLAUDE.md"
  destination  = "~/.claude/CLAUDE.md"
  stage_source = true
}
