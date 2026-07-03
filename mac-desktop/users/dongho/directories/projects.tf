resource "host_dir" "projects" {
  path = "~/projects"
  mode = "0755"
}

resource "host_git_repo" "environments" {
  url  = "git@github.com:dongho-jung/environments.git"
  path = "${host_dir.projects.path}/environments"

  delete_on_destroy = false
}

resource "host_git_repo" "shell_history" {
  url  = "git@github.com:dongho-jung/shell-history.git"
  path = "${host_dir.projects.path}/shell-history"

  delete_on_destroy = false
}

resource "host_git_repo" "terraform_provider_host" {
  url  = "git@github.com:dongho-jung/terraform-provider-host.git"
  path = "${host_dir.projects.path}/terraform-provider-host"

  delete_on_destroy = false
}

resource "host_git_repo" "vault" {
  url  = "git@github.com:dongho-jung/vault.git"
  path = "${host_dir.projects.path}/vault"

  delete_on_destroy = false
}
