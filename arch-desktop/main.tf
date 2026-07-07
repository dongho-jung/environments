terraform {
  required_providers {
    host = {
      source  = "dongho-jung/host"
      version = "~> 0.11.0"
    }
  }
}

provider "host" {
  target_user = "dongho"
  home_dir    = "/home/dongho"
}
