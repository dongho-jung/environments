resource "host_package_brew" "rust" {
  name = "rust"
}

resource "host_file_block" "rust_path" {
  block   = host_file.zshrc.blocks.path
  content = "export PATH=\"$PATH:$HOME/.cargo/bin\""
}
