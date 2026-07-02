resource "host_package_brew" "terraform" {
  name = "terraform"
  tap  = "hashicorp/tap"
}

resource "host_package_brew" "terraform_ls" {
  name = "terraform-ls"
}

resource "host_file_block" "terraform_aliases" {
  block   = host_file.zshrc.blocks.alias
  content = "alias tf='terraform' tfi='tf init' tfp='tf plan' tfa='terraform apply'"
}
