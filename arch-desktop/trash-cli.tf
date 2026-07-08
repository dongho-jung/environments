# Backs the `rm is disabled, use trash instead` alias in zsh.tf -- until now
# that alias pointed at a command that was never installed.
resource "host_package_pacman" "trash_cli" {
  name = "trash-cli"
}
