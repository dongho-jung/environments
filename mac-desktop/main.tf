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
