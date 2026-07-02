resource "host_package_brew" "codex" {
  name         = "codex"
  package_type = "cask"
}

resource "host_file_block" "codex_aliases" {
  block   = host_file.zshrc.blocks.alias
  content = "alias o='codex --dangerously-bypass-approvals-and-sandbox'"
}
