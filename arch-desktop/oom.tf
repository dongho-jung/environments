# On 2026-08-06 this machine hard-froze under memory exhaustion and had to be
# power-cycled. With no swap configured the kernel's only reclaim target was page
# cache, which collapsed to 2.6 MB while 30.2 GiB of the 31.3 GiB usable RAM sat
# in anonymous pages. Every process then faulted its own text back off disk on
# each instruction, so the compositor, the input stack and journald all stalled
# together and the OOM killer never got far enough ahead to end it.
#
# The two resources below attack opposite halves of that. zram gives reclaim
# somewhere to put anonymous pages so page cache is no longer the only thing that
# can be evicted, and earlyoom ends the episode outright while the machine is
# still responsive enough to act. Neither is sufficient alone: zram only moves
# the wall further out, and earlyoom cannot be scheduled once the livelock has
# already started.

resource "host_package_pacman" "zram_generator" {
  name = "zram-generator"
}

# 8 GiB of zram costs roughly 3 GiB of real memory once full at zstd's typical
# ratio on this workload. Sizing it larger would buy more headroom but also
# lengthen the thrashing this is meant to cut short, so the ceiling stays low and
# earlyoom is left to end the episode.
resource "host_system_file" "zram_generator_config" {
  source      = "${path.module}/oom/zram-generator.conf"
  destination = "/etc/systemd/zram-generator.conf"

  mode              = "0644"
  adopt_existing    = true
  delete_on_destroy = true

  depends_on = [
    host_package_pacman.zram_generator,
  ]
}

# Nothing activates the device here on purpose. zram-generator is a systemd
# generator: it reads the file above on every daemon-reload, writes dev-zram0.swap
# under /run and links it into swap.target, so each boot reconciles the device
# from this config on its own. There is no unit to enable, and host_systemd_service
# only manages .service units in any case. Editing the sizing therefore takes
# effect on the next boot, or immediately with:
#
#   sudo systemctl daemon-reload && sudo systemctl restart dev-zram0.swap

# Swapping to zram costs CPU rather than disk seeks, so the kernel should reach
# for it well before it starts evicting executable pages -- that eviction is
# exactly what turned this incident into a freeze. 180 is the value the zram
# maintainers recommend for swap-on-zram; the stock 60 is tuned for rotating
# disks and would keep sacrificing page cache first.
resource "host_sysctl" "vm_swappiness" {
  key   = "vm.swappiness"
  value = "180"
}

# Swap readahead is a disk optimisation. zram is random-access, so reading
# neighbouring pages only burns decompression cycles on pages nobody asked for.
resource "host_sysctl" "vm_page_cluster" {
  key   = "vm.page-cluster"
  value = "0"
}

# Wake kswapd further from the low watermark than the default 10 does. Background
# reclaim then has room to keep up, instead of allocations dropping into direct
# reclaim where every thread blocks on its own page faults.
resource "host_sysctl" "vm_watermark_scale_factor" {
  key   = "vm.watermark_scale_factor"
  value = "125"
}

resource "host_package_pacman" "earlyoom" {
  name = "earlyoom"
}

# Replaces the file the package ships, so it is adopted rather than created and
# left behind on destroy for pacman to keep owning.
resource "host_system_file" "earlyoom_config" {
  source      = "${path.module}/oom/earlyoom"
  destination = "/etc/default/earlyoom"

  mode              = "0644"
  adopt_existing    = true
  delete_on_destroy = false

  depends_on = [
    host_package_pacman.earlyoom,
  ]
}

resource "host_systemd_service" "earlyoom" {
  name            = "earlyoom.service"
  enabled         = true
  running         = true
  restart_trigger = filesha256("${path.module}/oom/earlyoom")

  depends_on = [
    host_system_file.earlyoom_config,
  ]
}
