resource "host_mac_dock_app" "system_settings" {
  path     = "/System/Applications/System Settings.app"
  priority = 10
}

resource "host_mac_dock_folder" "downloads" {
  path     = "~/Downloads"
  priority = 10
}
