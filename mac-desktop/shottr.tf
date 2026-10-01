resource "host_package_brew" "shottr" {
  name         = "shottr"
  package_type = "cask"
}

resource "host_mac_login_item" "shottr" {
  path = host_package_brew.shottr.app_path
}

# The panel settings as they are configured now. keyboard.tf turns the built-in
# screenshot shortcuts off so these bindings own Cmd+Shift+3 and Cmd+Shift+4.
# Update checks, the license vault, the telemetry queue and first-run flags are
# app state, not configuration, and stay out.
resource "host_mac_settings" "shottr" {
  groups = {
    "cc.ffitch.shottr" = {
      # Carbon key codes: 18 is 3, 19 is 2, 20 is 4, 29 is 0. 768 is Cmd+Shift.
      KeyboardShortcuts_fullscreen = "{\"carbonKeyCode\":18,\"carbonModifiers\":768}"
      KeyboardShortcuts_area       = "{\"carbonModifiers\":768,\"carbonKeyCode\":20}"
      KeyboardShortcuts_scrolling  = "{\"carbonKeyCode\":19,\"carbonModifiers\":768}"
      KeyboardShortcuts_repeatArea = "{\"carbonModifiers\":768,\"carbonKeyCode\":29}"
      KeyboardShortcuts_ocr        = false

      # A grab opens the editor and lands on the clipboard, never on disk.
      areaCaptureMode = "editor"
      afterGrabCopy   = true
      afterGrabSave   = false
      afterGrabShow   = true
      copyOnEsc       = true
      saveOnEsc       = false

      captureCursor = "auto"
      colorFormat   = "HEX"
      saveFormat    = "PNG"
    }
  }

  depends_on = [host_package_brew.shottr]
}
