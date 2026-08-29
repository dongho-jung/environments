resource "host_dir" "local_bin" {
  path = "~/.local/bin"
  mode = "0755"
}

resource "host_file_block" "local_bin_path" {
  block   = host_file.zshrc.blocks.path
  content = "export PATH=\"$HOME/.local/bin:$PATH\""
}

# Build the clean Myriad checkout into one statically linked executable and
# replace the live binary atomically. All shell launchers, hooks, status output,
# supervision, and lifecycle operations go through this binary.
resource "terraform_data" "myriad_binary" {
  triggers_replace = {
    commit = host_git_repo.myriad.commit
  }

  lifecycle {
    precondition {
      condition     = !host_git_repo.myriad.dirty
      error_message = "Refusing to build Myriad from a dirty checkout. Commit the Myriad repository first."
    }
  }

  provisioner "local-exec" {
    working_dir = host_git_repo.myriad.path_resolved
    interpreter = ["/usr/bin/zsh", "-c"]

    command = <<-EOT
      set -euo pipefail

      install_path="${host_dir.local_bin.path_resolved}/myriad"
      temporary_path="$(mktemp "$${install_path}.tmp.XXXXXX")"
      trap 'rm -f "$temporary_path"' EXIT

      CGO_ENABLED=0 go build \
        -mod=readonly \
        -trimpath \
        -ldflags '-s -w -X github.com/dongho-jung/myriad/internal/myriad.Version=${host_git_repo.myriad.commit}' \
        -o "$temporary_path" \
        ./cmd/myriad
      chmod 0755 "$temporary_path"
      mv -f "$temporary_path" "$install_path"
      trap - EXIT
    EOT
  }

  depends_on = [
    host_dir.local_bin,
    host_package_pacman.git,
    host_package_pacman.go,
  ]
}

# Keep the shell contract intentionally thin. Myriad owns argument routing and
# the complete Codex/Claude lifecycle so configuration cannot drift from the
# tested executable.
resource "host_file_block" "myriad_launchers" {
  block = host_file.zshrc.blocks.functions

  content = <<-EOT
    o() {
      command myriad codex "$@"
    }

    c() {
      command myriad claude "$@"
    }
  EOT

  depends_on = [terraform_data.myriad_binary]
}

# Reconcile abrupt launcher exits independently from coding-agent behavior.
resource "host_schedule" "myriad_reconcile" {
  schedule          = "17 * * * *"
  shell             = "/usr/bin/zsh"
  working_directory = host_dir.projects.path_resolved

  environment = {
    PATH = "${host_dir.local_bin.path_resolved}:/usr/local/bin:/usr/bin:/bin"
  }

  command = "myriad reconcile --quiet"

  depends_on = [
    terraform_data.myriad_binary,
    host_systemd_service.cronie,
  ]
}
