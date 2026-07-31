terraform {
  required_providers {
    host = {
      source  = "dongho-jung/host"
      version = "~> 0.17.0"
    }
  }
}

provider "host" {
  target_user = "dongho"
  aur_helper  = "yay"
}
