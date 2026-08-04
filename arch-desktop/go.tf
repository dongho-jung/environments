resource "host_package_pacman" "go" {
  name = "go"
}

# golangci-lint comes from the repositories rather than `go install` so its
# version tracks Arch instead of drifting from CI, which pins `latest`.
resource "host_package_pacman" "golangci_lint" {
  name = "golangci-lint"
}

# `go install` writes here, and the terraform-provider-host dev_overrides entry
# reads the provider binary from the same directory.
#
# Appended rather than prepended, unlike the other PATH entries: a leftover
# `go install` build of a tool that is also packaged, such as golangci-lint,
# would otherwise shadow the managed one and silently lint at an older version.
resource "host_file_block" "go_path" {
  block   = host_file.zshrc.blocks.path
  content = "export PATH=\"$PATH:$HOME/go/bin\""
}
