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

  # Terraform configures a provider once per graph walk and `terraform apply`
  # walks twice, so pre-authentication asked for the password twice on every
  # run, including runs that change nothing. Nothing here reads or writes
  # anything root owns; only a cask install or removal does, and that path
  # authenticates on demand and holds the timestamp for the rest of the run.
  #
  # A fresh machine is still asked once, up front: bootstrap.sh is the entry
  # point there, and it authenticates sudo before Terraform starts and refreshes
  # the timestamp every 50 seconds for the whole run, which is what keeps the
  # provider quiet. Running `terraform apply` by hand on a machine that still
  # has casks to install is the one case that prompts mid-run; `sudo -v` first
  # puts that prompt back at the top.
  sudo_preauth = false
}
