resource "host_package_pacman" "terraform" {
  name = "terraform"
}

# NOTE: terraform-ls is only in the AUR. The host_package_pacman resource shells
# out to plain `pacman`, which cannot build AUR packages, so it is intentionally
# omitted here. Install it manually with `yay -S terraform-ls` if desired.

resource "host_file_block" "terraform_aliases" {
  block   = host_file.zshrc.blocks.alias
  content = "alias tf='terraform' tfi='tf init' tfp='tf plan' tfa='terraform apply'"
}
