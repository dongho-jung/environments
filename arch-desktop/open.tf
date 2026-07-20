# macOS-style `open FILE|DIR|URL [...]` support. `gio open` accepts multiple
# targets and delegates each one to the desktop's MIME association.
resource "host_package_pacman" "glib2" {
  name = "glib2"
}

# Dedicated player for recordings and other local audio/video files.
resource "host_package_pacman" "mpv" {
  name = "mpv"
}

# Desktop-specific defaults take precedence in a Hyprland session without
# replacing ~/.config/mimeapps.list, which other applications update directly.
resource "host_file" "hyprland_mimeapps" {
  path = "~/.config/hyprland-mimeapps.list"

  content = <<-EOT
    [Default Applications]
    inode/directory=org.kde.dolphin.desktop
    video/mp4=mpv.desktop
    video/x-matroska=mpv.desktop
    video/webm=mpv.desktop
    video/quicktime=mpv.desktop
    video/x-msvideo=mpv.desktop
    audio/mpeg=mpv.desktop
    audio/flac=mpv.desktop
    audio/ogg=mpv.desktop
    audio/x-wav=mpv.desktop
    application/ogg=mpv.desktop
  EOT

  depends_on = [
    host_package_pacman.dolphin,
    host_package_pacman.mpv,
  ]
}

resource "host_file_block" "open_function" {
  block = host_file.zshrc.blocks.functions

  content = <<-EOT
    open() {
      if (( $# == 0 )); then
        print -u2 -- 'usage: open FILE|DIR|URL [...]'
        return 2
      fi

      command gio open -- "$@"
    }
    compdef _files open
  EOT

  depends_on = [
    host_package_pacman.glib2,
  ]
}
