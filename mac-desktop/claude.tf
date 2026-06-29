resource "host_package_brew" "claude" {
  name         = "claude"
  package_type = "cask"
}

resource "host_file_block" "claude_aliases" {
  file_block = host_file.zshrc.block["alias"]
  priority   = 10
  content    = "alias c='IS_DEMO=1 claude --ide --chrome --allow-dangerously-skip-permissions --effort max --permission-mode bypassPermissions'"
}
