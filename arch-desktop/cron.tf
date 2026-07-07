# `host_schedule` (see the shell-history auto-commit in git.tf) manages entries in
# the target user's crontab, which needs the `crontab` binary plus a running cron
# daemon. On Arch that is the `cronie` package and `cronie.service`. The provider
# only auto-installs cron on DNF-based systems (and would try to start Fedora's
# `crond.service`), so manage cronie explicitly here, mirroring docker.tf.
resource "host_package_pacman" "cronie" {
  name = "cronie"
}

resource "host_systemd_service" "cronie" {
  name    = "cronie.service"
  enabled = true
  running = true

  depends_on = [
    host_package_pacman.cronie,
  ]
}
