terraform {
  required_version = ">= 1.0"

  required_providers {
    host = {
      source = "dongho-jung/host"
    }
  }
}

locals {
  dongho_username = "dongho"
  dongho_home_dir = "/Users/${local.dongho_username}"
}

provider "host" {
  home_dir = local.dongho_home_dir
}

module "dongho" {
  source = "./users/dongho"

  depends_on = [
    host_user.dongho,
  ]
}
