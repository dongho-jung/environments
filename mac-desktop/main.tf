terraform {
  required_providers {
    host = {
      source  = "dongho-jung/host"
      version = ">= 0.10.0"
    }
  }
}

provider "host" {
  target_user = "dongho"
}
