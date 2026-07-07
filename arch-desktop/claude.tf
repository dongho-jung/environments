# The `claude` CLI is provided by the AUR `claude-code` package. host_package_pacman
# uses plain `pacman` and cannot build from the AUR, so this resource only manages
# the already-installed package (imported below in imports.tf). To (re)install on a
# fresh machine, build it first with `yay -S claude-code`.
resource "host_package_pacman" "claude_code" {
  name           = "claude-code"
  ignore_version = true
}

resource "host_file_block" "claude_aliases" {
  block   = host_file.zshrc.blocks.alias
  content = "alias c='IS_DEMO=1 claude --ide --chrome --allow-dangerously-skip-permissions --effort max --permission-mode bypassPermissions'"
}

resource "host_link" "claude_settings" {
  source      = "claude/settings.json"
  destination = "~/.claude/settings.json"
}

resource "host_link" "claude_command_c" {
  source      = "../common/claude/commands/c.md"
  destination = "~/.claude/commands/c.md"
}

resource "host_link" "claude_command_new_version" {
  source      = "../common/claude/commands/new-version.md"
  destination = "~/.claude/commands/new-version.md"
}
