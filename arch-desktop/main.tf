terraform {
  required_version = ">= 1.7, < 2.0"

  backend "local" {
    path = "/home/dongho/.local/state/terraform/arch-desktop/terraform.tfstate"
  }

  required_providers {
    host = {
      source  = "dongho-jung/host"
      version = "~> 0.17.1"
    }
  }
}

provider "host" {
  target_user                  = "dongho"
  aur_helper                   = "yay"
  aur_remove_make_dependencies = true
  aur_clean_after              = true
}
