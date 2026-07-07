# Wayland desktop integration glue that Hyprland relies on but that has no config
# of its own here.

# Portal backend: screen sharing, screenshots and native file pickers for apps.
resource "host_package_pacman" "xdg_desktop_portal_hyprland" {
  name = "xdg-desktop-portal-hyprland"
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
