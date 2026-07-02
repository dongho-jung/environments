terraform {
  required_version = ">= 1.0"

  required_providers {
    host = {
      source  = "dongho-jung/host"
      version = "0.1.0"
    }
  }
}

provider "host" {}

module "dongho" {
  source = "./users/dongho"

  depends_on = [
    host_user.dongho,
  ]
}
