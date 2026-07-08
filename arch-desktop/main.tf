terraform {
  required_providers {
    host = {
      source  = "dongho-jung/host"
      version = "~> 0.12.0"
    }
  }
}

provider "host" {
  target_user = "dongho"
  home_dir    = "/home/dongho"
}
