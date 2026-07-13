resource "host_package_pacman" "rust" {
  # Arch's rust package provides both the rustc and cargo binaries.
  name = "rust"
}

resource "host_file_block" "cargo_path" {
  block   = host_file.zshrc.blocks.path
  content = "export PATH=\"$HOME/.cargo/bin:$PATH\""
}
