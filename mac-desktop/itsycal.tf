resource "host_package_brew" "itsycal" {
  name         = "itsycal"
  package_type = "cask"
}

resource "host_mac_login_item" "itsycal" {
  path = host_package_brew.itsycal.app_path
}

# Menu bar clock. `[w]` is the ISO week number and the calendar icon is hidden,
# so the menu bar shows only the text, as in `[39] 26-09-26 土 00:08:52`. The
# weekday letter follows the system language. Itsycal reads these at launch and
# writes them back on quit, so change them here and restart it, not in its panel.
resource "host_mac_settings" "itsycal" {
  groups = {
    "com.mowglii.ItsycalApp" = {
      ClockFormat   = "[w] yy-MM-dd E HH:mm:ss"
      HideIcon      = true
      ShowEventDays = 7
    }
  }

  depends_on = [host_package_brew.itsycal]
}
