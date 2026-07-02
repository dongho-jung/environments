resource "host_macos_default" "clock_analog" {
  domain = "com.apple.menuextra.clock"
  key    = "IsAnalog"
  bool   = true
}

resource "host_macos_default" "clock_show_ampm" {
  domain = "com.apple.menuextra.clock"
  key    = "ShowAMPM"
  bool   = true
}

resource "host_macos_default" "clock_show_date" {
  domain = "com.apple.menuextra.clock"
  key    = "ShowDate"
  int    = 2
}

resource "host_macos_default" "clock_show_day_of_week" {
  domain = "com.apple.menuextra.clock"
  key    = "ShowDayOfWeek"
  bool   = false
}
