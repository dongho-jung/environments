terraform {
  required_providers {
    host = {
      source = "dongho-jung/host"
    }
  }
}

provider "host" {
  target_user = "dongho"
}

module "dongho" {
  source = "./users/dongho"

  depends_on = [
    host_user.dongho,
  ]
}
