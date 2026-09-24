resource "host_package_brew" "iterm2" {
  name         = "iterm2"
  package_type = "cask"
}

# Keep the archived Mac Air preferences as the source of truth. Use a copy so
# iTerm cannot rewrite the repository file when saving its preferences.
resource "host_file" "iterm2_preferences" {
  path    = "~/.config/iterm2/com.googlecode.iterm2.plist"
  content = file("${path.module}/../others/mac-air/configs/iterm2/com.googlecode.iterm2.plist")
}

# iTerm reads custom preferences at startup; restart it after applying changes.
resource "host_mac_settings" "iterm2" {
  groups = {
    "com.googlecode.iterm2" = {
      LoadPrefsFromCustomFolder = true
      PrefsCustomFolder         = dirname(host_file.iterm2_preferences.path_resolved)
      # Keep GUI changes from overwriting the Terraform-managed preferences.
      NoSyncNeverRemindPrefsChangesLostForFile           = true
      NoSyncNeverRemindPrefsChangesLostForFile_selection = 1
    }
  }

  depends_on = [host_package_brew.iterm2]
}
