terraform {
  required_providers {
    host = {
      source  = "dongho-jung/host"
      version = "~> 0.17.0"
    }
  }
}

provider "host" {
  target_user                  = "dongho"
  aur_helper                   = "yay"
  aur_remove_make_dependencies = true
  aur_clean_after              = true
}
