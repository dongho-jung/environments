# The RTX 2070 has repeatedly exhausted BAR1 VA mappings in nvidia-open while
# Chromium was using the GPU. Keep GSP, DPMS, and application acceleration at
# their defaults, but replace the open kernel module with NVIDIA's proprietary
# module from the same 610 feature branch.

# DKMS needs headers for every kernel it builds the NVIDIA module against.
resource "host_package_pacman" "linux_headers" {
  name = "linux-headers"
}

resource "host_package_pacman" "dkms" {
  name = "dkms"
}

# Both replacement packages have to enter the same pacman transaction. The host
# provider invokes yay with --noconfirm, whose default answer to a package
# conflict is "no". Pacman's question mask 4 reverses only conflict-removal
# answers, allowing these two expected replacements without enabling a blanket
# "yes" for unrelated prompts. This migration is recorded once in Terraform
# state; the package resource below manages steady-state presence afterwards.
resource "terraform_data" "nvidia_proprietary_transition" {
  triggers_replace = "nvidia-open-to-nvidia-beta-dkms"

  provisioner "local-exec" {
    command = "yay -S --needed --noconfirm --ask=4 nvidia-beta-dkms"
  }

  depends_on = [
    host_package_pacman.dkms,
    host_package_pacman.linux_headers,
  ]
}

# nvidia-beta-dkms has an exact-version dependency on nvidia-utils-beta. Keep
# the userspace package implicit so yay replaces nvidia-open and nvidia-utils
# together instead of Terraform racing two conflicting package resources. Like
# the other AUR resources in this workspace, this manages presence; upgrades
# remain an explicit package-maintenance action.
resource "host_package_aur" "nvidia_proprietary_dkms" {
  name = "nvidia-beta-dkms"

  depends_on = [terraform_data.nvidia_proprietary_transition]
}
