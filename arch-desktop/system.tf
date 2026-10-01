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

# systemd ships 16, which enables sync and nothing else. During the 2026-08-06
# memory freeze (see oom.tf) every REISUB key past the S was silently dropped by
# the kernel, so the only way out was the power button. This is a single-user
# desktop, so the usual argument for withholding the reboot and signal keys from
# whoever is at the keyboard does not apply.
resource "host_sysctl" "kernel_sysrq" {
  key   = "kernel.sysrq"
  value = "1"
}

# /boot is the vfat EFI system partition with fsck pass 2 in fstab, but the
# base install never pulled in dosfstools, so systemd-fsck had no fsck.vfat to
# run and the dirty bit left by the 2026-10-01 forced power-off stayed set
# ("Volume was not properly unmounted" on every boot). With the package present
# the ESP is checked and cleaned at boot like the ext4 filesystems.
resource "host_package_pacman" "dosfstools" {
  name = "dosfstools"
}
