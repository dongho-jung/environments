resource "host_package_brew" "iterm2" {
  name         = "iterm2"
  package_type = "cask"
}

# The archived profiles name Mac Air fonts: Tab0MonoK is not installed here and
# Menlo has no Nerd Font glyphs, so Starship's Git branch symbol (U+E0A0) falls
# back to the system last-resort box. Both profiles use the Nerd Font instead.
# Inconsolata is narrower than Menlo, so 13 pt keeps the rendered size of 11 pt.
locals {
  iterm2_preferences = replace(
    replace(
      file("${path.module}/../others/mac-air/configs/iterm2/com.googlecode.iterm2.plist"),
      "<string>Tab0MonoK-Regular 14</string>",
      "<string>InconsolataNFM-Regular 14</string>",
    ),
    "<string>Menlo-Regular 11</string>",
    "<string>InconsolataNFM-Regular 13</string>",
  )
}

# Keep the archived Mac Air preferences as the source of truth. Use a copy so
# iTerm cannot rewrite the repository file when saving its preferences.
resource "host_file" "iterm2_preferences" {
  path    = "~/.config/iterm2/com.googlecode.iterm2.plist"
  content = local.iterm2_preferences

  depends_on = [host_package_brew.font_inconsolata_nerd_font]
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
