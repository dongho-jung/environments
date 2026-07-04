terraform {
  required_providers {
    host = {
      source = "dongho-jung/host"
    }
  }
}

module "packages" {
  source = "./packages"
}

module "mac" {
  source = "./mac"
}
