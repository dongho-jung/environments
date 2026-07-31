terraform {
  required_providers {
    host = {
      source  = "dongho-jung/host"
      version = "~> 0.16.0"
    }
  }
}

provider "host" {
  target_user = "dongho"
  home_dir    = "/home/dongho"
  runtime_dir = "/home/dongho/.local/state/terraform-provider-host"
  aur_helper  = "yay"
}
