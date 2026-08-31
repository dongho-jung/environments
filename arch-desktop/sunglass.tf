resource "host_dir" "local_libexec" {
  path = "~/.local/libexec"
  mode = "0755"
}

resource "host_link" "sunglass" {
  source       = "${host_git_repo.sunglass.path_resolved}/src/sunglass"
  destination  = "${host_dir.local_libexec.path}/sunglass"
  stage_source = true

  lifecycle {
    precondition {
      condition     = !host_git_repo.sunglass.dirty
      error_message = "Refusing to deploy Sunglass from a dirty checkout. Commit the private repository first."
    }
  }

  depends_on = [
    host_dir.local_libexec,
    host_git_repo.sunglass,
  ]
}
