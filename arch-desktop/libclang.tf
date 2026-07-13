resource "host_package_pacman" "libclang" {
  # Arch ships libclang as part of the clang package.
  name = "clang"
}
