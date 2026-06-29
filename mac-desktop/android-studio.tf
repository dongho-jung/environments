resource "host_package_brew" "android_studio" {
  name         = "android-studio"
  package_type = "cask"
}

resource "host_file_block" "android_studio_path" {
  file_block = host_file.zshrc.block["path"]
  priority   = 10
  content    = "export PATH=\"$PATH:$HOME/Library/Android/sdk/platform-tools/\""
}
