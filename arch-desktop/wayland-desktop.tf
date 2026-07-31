# Wayland desktop integration glue that Hyprland relies on but that has no config
# of its own here.

# Portal broker plus the Hyprland and GTK backends.
resource "host_package_pacman" "xdg_desktop_portal" {
  name = "xdg-desktop-portal"
}

# Portal backend: screen sharing, screenshots and native file pickers for apps.
resource "host_package_pacman" "xdg_desktop_portal_hyprland" {
  name = "xdg-desktop-portal-hyprland"
}

# GTK portal supplies the native file chooser used alongside the Hyprland
# screen-sharing portal.
resource "host_package_pacman" "xdg_desktop_portal_gtk" {
  name = "xdg-desktop-portal-gtk"
}

# XWayland keeps applications without native Wayland support usable.
resource "host_package_pacman" "xorg_xwayland" {
  name = "xorg-xwayland"
}

# Creates the standard Desktop, Downloads, Documents, and media directories.
resource "host_package_pacman" "xdg_user_dirs" {
  name = "xdg-user-dirs"
}

# Wayland input-event viewer used to identify hardware keys while editing the
# Hyprland and keyd bindings.
resource "host_package_pacman" "wev" {
  name = "wev"
}

# PolicyKit authentication agent so privileged prompts get a GUI dialog.
resource "host_package_pacman" "polkit_kde_agent" {
  name = "polkit-kde-agent"
}

# Qt Wayland platform plugins so Qt5/Qt6 apps run natively on Wayland.
resource "host_package_pacman" "qt5_wayland" {
  name = "qt5-wayland"
}

resource "host_package_pacman" "qt6_wayland" {
  name = "qt6-wayland"
}
