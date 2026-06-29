resource "host_package_brew" "rust" {
  name = "rust"
}

resource "host_file_block" "rust_path" {
  file_block = host_file.zshrc.block["path"]
  priority   = 20
  content    = "export PATH=\"$PATH:$HOME/.cargo/bin\""
}
