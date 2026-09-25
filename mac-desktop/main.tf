terraform {
  required_providers {
    host = {
      source = "dongho-jung/host"
    }
  }
}

provider "host" {
  target_user = "dongho"
  home_dir    = "/Users/dongho"

  # Nothing here reads or writes anything root owns, so a converged run needs no
  # password at all. Only a cask install or removal does, and it authenticates
  # on demand. Pre-authentication would instead prompt once per graph walk, and
  # `terraform apply` walks twice, so it asked for the password twice per run.
  sudo_preauth = false
}
