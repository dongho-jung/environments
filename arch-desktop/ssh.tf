resource "host_package_pacman" "openssh" {
  name = "openssh"
}

resource "host_ssh_key" "github" {
  path              = "~/.ssh/id_ed25519"
  comment           = "dongho971220@gmail.com"
  delete_on_destroy = false

  depends_on = [
    host_package_pacman.openssh,
  ]
}

# Pinned from GitHub's published SSH host keys. Keeping this separate from the
# general known_hosts file preserves entries learned for other hosts.
resource "host_file" "github_known_hosts" {
  path = "~/.ssh/known_hosts.github"

  content = <<-EOT
    github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl
    github.com ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg=
    github.com ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1aNUkY4Ue1gvwnGLVlOhGeYrnZaMgRK6+PKCUXaDbC7qtbW8gIkhL7aGCsOr/C56SJMy/BCZfxd1nWzAOxSDPgVsmerOBYfNqltV9/hWCqBywINIR+5dIg6JTJ72pcEpEjcYgXkE2YEFXV1JHnsKgbLWNlhScqb2UmyRkQyytRLtL+38TGxkxCflmO+5Z8CSSNY7GidjMIZ7Q4zMjA2n1nGrlTDkzwDCsw+wqFPGQA179cnfGWOWRVruj16z6XyvxvjJwbz0wQZ75XK5tKSb7FNyeIEs4TT4jk+S4dhPeAUC5y+bDYirYgM4GC7uEnztnZyaVWQ7B381AK4Qdrwt51ZqExKbQpTUNn+EjqoTwvqNj4kqx5QUCI0ThS/YkOxJCXmPUWZbhjpCg56i+2aB6CmK2JGhn57K5mj0MNdBXA4/WnwH6XoPWJzK5Nyu2zB3nAZp+S5hpQs+p1vN1/wsjk=
  EOT

  depends_on = [
    host_ssh_key.github,
  ]
}

# A newly generated public key still has to be registered with the GitHub
# account out of band before the first private-repository clone can succeed.
resource "host_ssh_config_host" "github" {
  host            = "github.com"
  hostname        = "github.com"
  user            = "git"
  identity_file   = host_ssh_key.github.path
  identities_only = true
  adopt_existing  = true

  extra_options = {
    AddKeysToAgent        = "yes"
    StrictHostKeyChecking = "yes"
    UserKnownHostsFile    = "/home/dongho/.ssh/known_hosts.github /home/dongho/.ssh/known_hosts"
  }

  depends_on = [
    host_file.github_known_hosts,
  ]
}
