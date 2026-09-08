# Steam needs multilib and the 32-bit userspace matching our NVIDIA beta driver.
resource "host_system_file" "pacman_config" {
  source         = "${path.module}/pacman.conf"
  destination    = "/etc/pacman.conf"
  mode           = "0644"
  adopt_existing = true
}

# Initialize only the newly enabled repository. Refreshing core/extra here
# would turn installing Steam into an unrelated system-upgrade operation.
resource "terraform_data" "steam_multilib_sync" {
  triggers_replace = host_system_file.pacman_config.checksum_sha256

  provisioner "local-exec" {
    interpreter = ["/usr/bin/bash", "-c"]
    command     = <<-EOT
      set -euo pipefail
      steam_config=$(mktemp)
      trap 'rm -f "$steam_config"' EXIT
      pacman-conf --config='${path.module}/pacman.conf' |
        awk '/^\[/ { selected = ($0 == "[options]" || $0 == "[multilib]") } selected' > "$steam_config"
      sudo pacman --sync --refresh --noconfirm --config "$steam_config"
    EOT
  }
}

# Install this provider of lib32-vulkan-driver before Steam so Pacman does not
# select the conflicting repository lib32-nvidia-utils package. Upgrade these
# libraries together with nvidia-utils-beta during driver maintenance.
resource "host_package_aur" "lib32_nvidia_utils_beta" {
  name = "lib32-nvidia-utils-beta"

  depends_on = [
    terraform_data.steam_multilib_sync,
    host_package_aur.nvidia_proprietary_dkms,
  ]
}

resource "host_package_pacman" "steam" {
  name = "steam"

  depends_on = [host_package_aur.lib32_nvidia_utils_beta]
}
