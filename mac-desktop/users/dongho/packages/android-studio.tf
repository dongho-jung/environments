resource "host_package_brew" "android_studio" {
  name         = "android-studio"
  package_type = "cask"
}

resource "host_file_block" "android_studio_path" {
  block   = host_file.zshrc.blocks.path
  content = "export PATH=\"$PATH:$HOME/Library/Android/sdk/platform-tools/\""
}
