# On 2026-10-01 17:01:28 the RTX 2070's power-management microcontroller halted
# (NVRM Xid 62, PMU_HALT_ERROR) while the kernel kept running: the display froze,
# cron and Docker kept logging, and the session ended with the power button
# nineteen seconds later. The journal held exactly one line about it, the
# eight-word Xid itself. Hyprland's own log lives in $XDG_RUNTIME_DIR and
# vanished with the reboot, and hypridle's lock/DPMS transitions were never
# logged, so whether a DPMS cycle preceded the halt is unknowable. These
# resources make sure the next freeze leaves something to read.

# The driver forwards GPU firmware (GSP-RM) logs to the kernel log only on debug
# builds (EnableGpuFirmwareLogs=2). Value 1 forwards them on release builds too,
# which is where the context around a PMU halt ends up. The option is read when
# the module loads, so it takes effect on the next boot. nvidia is not in the
# initramfs (MODULES=() and the kms hook only picks in-tree DRM drivers), so no
# mkinitcpio run is needed.
resource "host_system_file" "nvidia_firmware_logs" {
  source      = "${path.module}/forensics/nvidia-firmware-logs.conf"
  destination = "/etc/modprobe.d/nvidia-firmware-logs.conf"

  mode              = "0644"
  delete_on_destroy = true

  depends_on = [
    host_package_aur.nvidia_proprietary_dkms,
  ]
}

# Follows the kernel log and, on an Xid, "fallen off the bus", lockup, hung-task
# or RCU-stall line, snapshots nvidia-smi, nvidia-bug-report, the NVIDIA /proc
# tree, lspci, sensors, the last 15 minutes of journal and every live Hyprland
# log into /var/log/gpu-xid/<timestamp>/, then syncs so a following power cycle
# cannot take the evidence with it. GPU-touching collectors run in the
# background under timeouts, so a wedged GPU cannot stall the sync.
# `sudo gpu-xid-capture capture manual` takes a snapshot on demand.
resource "host_system_file" "gpu_xid_capture" {
  source      = "${path.module}/forensics/gpu-xid-capture"
  destination = "/usr/local/bin/gpu-xid-capture"

  mode              = "0755"
  delete_on_destroy = true
}

resource "host_systemd_unit" "gpu_xid_capture" {
  name    = "gpu-xid-capture.service"
  content = file("${path.module}/forensics/gpu-xid-capture.service")

  depends_on = [
    host_system_file.gpu_xid_capture,
  ]
}

resource "host_systemd_service" "gpu_xid_capture" {
  name    = "gpu-xid-capture.service"
  enabled = true
  running = true
  restart_trigger = sha256(join("", [
    filesha256("${path.module}/forensics/gpu-xid-capture"),
    filesha256("${path.module}/forensics/gpu-xid-capture.service"),
  ]))

  depends_on = [
    host_systemd_unit.gpu_xid_capture,
  ]
}

# journald fsyncs non-critical messages (which includes the KERN_ERR Xid line)
# every 5 minutes by default; a hand power cycle after a freeze loses whatever
# was still unsynced. 10s bounds that. Replaces the stock all-comment file, so
# it is adopted and left for pacman on destroy (same pattern as
# /etc/default/earlyoom). journald reads it at start: `sudo systemctl restart
# systemd-journald`, or the reboot the modprobe option needs anyway.
resource "host_system_file" "journald_config" {
  source      = "${path.module}/forensics/journald.conf"
  destination = "/etc/systemd/journald.conf"

  mode              = "0644"
  adopt_existing    = true
  delete_on_destroy = false
}
