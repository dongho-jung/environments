# Browser package managed through Pacman.
resource "host_package_pacman" "chromium" {
  name = "chromium"
}

# Chromium builds its renderer accessibility tree only with this flag; the
# org.a11y.Status screen-reader signal alone is ignored as of Chromium 150.
# wl-wysiwyc reads that tree to label clickable elements. The Arch launcher
# appends flags from this file to every chromium invocation.
resource "host_file" "chromium_flags" {
  path = "~/.config/chromium-flags.conf"

  content = <<-EOT
    --force-renderer-accessibility
  EOT

  depends_on = [
    host_package_pacman.chromium,
  ]
}
