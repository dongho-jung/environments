resource "host_package_aur" "slack" {
  name = "slack-desktop"
}

# Slack is Electron, so it needs the same accessibility flag as chromium.tf
# before it publishes an AT-SPI tree for wl-wysiwyc to label; without it the
# process never appears on the accessibility bus at all. Electron bundles its
# own Chromium and never reads chromium-flags.conf, so the flag has to go on
# the command line, which means overriding the packaged desktop entry. Entries
# in ~/.local/share/applications win over /usr/share/applications, and Slack
# has to be quit from its tray icon (not just closed) to pick this up.
resource "host_file" "slack_desktop" {
  path = "~/.local/share/applications/slack.desktop"

  content = <<-EOT
    [Desktop Entry]
    Name=Slack
    StartupWMClass=Slack
    Comment=Slack Desktop
    GenericName=Slack Client for Linux
    Exec=/usr/bin/slack --gtk-version=3 --force-renderer-accessibility -s %U
    Icon=slack
    Type=Application
    StartupNotify=true
    Categories=GNOME;GTK;Network;InstantMessaging;
    MimeType=x-scheme-handler/slack;
  EOT

  depends_on = [
    host_package_aur.slack,
  ]
}
