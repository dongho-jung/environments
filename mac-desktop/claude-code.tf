# The claude-code cask follows the stable channel, which trails the newest
# release by several versions. @latest follows every release and installs the
# same `claude` binary.
resource "host_package_brew" "claude_code" {
  name         = "claude-code@latest"
  package_type = "cask"
}
