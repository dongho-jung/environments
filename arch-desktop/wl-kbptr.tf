# Keyboard-driven mouse pointer for Wayland, bound to the Hangul key in
# hypr/hyprland.lua (`wl-kbptr -o modes=tile,bisect`): type a grid cell's letter
# label to jump near the target, then bisect (a/s/d/f/j/k/l/m) narrows to the exact
# pixel; g/h/b = left/right/middle-click there (Enter moves without clicking, Esc
# cancels). Tile grid density is hardcoded (max 26*26 cells, min cell 25*50 px), so
# bisect is chained for sub-cell precision. The `click` mode is intentionally NOT
# chained: it force-sets the button to left, which would break h/b right/middle-click.
#
# wl-kbptr is only in the AUR, so it is managed through host_package_aur,
# which builds and installs via yay/paru.
resource "host_package_aur" "wl_kbptr" {
  name = "wl-kbptr"
}
#
# NOTE: "floating" mode (auto-detecting on-screen targets, like vimium hints) needs
# wl-kbptr built with the opencv feature. The AUR package ships without it, and its
# meson build wants opencv4 while only opencv5 is installed -- so split mode is used.
