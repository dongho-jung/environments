terraform {
  required_version = ">= 1.7, < 2.0"

  backend "local" {
    path = "/home/dongho/.local/state/terraform/arch-desktop/terraform.tfstate"
  }

  required_providers {
    host = {
      source  = "dongho-jung/host"
      version = "~> 0.21.0"
    }
  }
}

provider "host" {}
