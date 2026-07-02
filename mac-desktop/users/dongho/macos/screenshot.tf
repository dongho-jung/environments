resource "host_macos_default" "screenshot_capture_delay" {
  domain = "com.apple.screencapture"
  key    = "captureDelay"
  float  = 5
}

resource "host_macos_default" "screenshot_show_clicks" {
  domain = "com.apple.screencapture"
  key    = "showsClicks"
  bool   = true
}

resource "host_macos_default" "screenshot_style" {
  domain = "com.apple.screencapture"
  key    = "style"
  string = "selection"
}

resource "host_macos_default" "screenshot_video" {
  domain = "com.apple.screencapture"
  key    = "video"
  bool   = true
}
