resource "host_package_brew" "codex" {
  name         = "codex"
  package_type = "cask"
}

resource "host_file_block" "codex_aliases" {
  file_block = host_file.zshrc.block["alias"]
  priority   = 20
  content    = "alias o='codex --dangerously-bypass-approvals-and-sandbox'"
}
