# Base system identity, already adopted into this workspace's state.
resource "host_hostname" "this" {
  name = "arch"
}

resource "host_timezone" "this" {
  name = "Asia/Seoul"
}

resource "host_locale" "this" {
  lang = "en_US.UTF-8"
}

# Pins the kernel's RAM-scaled default (524288 on this machine) so editors,
# LSP servers, and docker builds never hit watch exhaustion after a kernel
# heuristic change or on a smaller-RAM rebuild of this config.
resource "host_sysctl" "inotify_max_user_watches" {
  key   = "fs.inotify.max_user_watches"
  value = "524288"
}
