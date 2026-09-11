# The frontend Vite CLI is packaged as nodejs-vite; AUR's vite is a trace viewer.
resource "host_package_aur" "vite" {
  name = "nodejs-vite"

  depends_on = [
    host_package_pacman.nodejs,
    host_package_pacman.npm,
  ]
}
