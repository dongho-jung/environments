resource "host_ssh_key" "github" {
  path              = "~/.ssh/id_ed25519"
  comment           = "dongho971220@gmail.com"
  delete_on_destroy = false
}

resource "host_ssh_config_host" "github" {
  host           = "github.com"
  identity_file  = host_ssh_key.github.path
  adopt_existing = true

  extra_options = {
    AddKeysToAgent = "yes"
    UseKeychain    = "yes"
  }
}
