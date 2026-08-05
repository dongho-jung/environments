resource "host_package_pacman" "terraform" {
  name = "terraform"
}

# NOTE: terraform-ls is only in the AUR and is not installed today. If desired,
# declare it with host_package_aur (like claude-code) instead of installing by hand.

resource "host_file_block" "terraform_aliases" {
  block   = host_file.zshrc.blocks.alias
  content = "alias tf='terraform' tfi='tf init' tfp='tf plan' tfa='terraform apply'"
}
