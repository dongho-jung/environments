# QEMU/KVM desktop stack. qemu-desktop includes the SPICE, GTK, PipeWire and
# VirtIO display pieces used by virt-manager's graphical console.
resource "host_package_pacman" "qemu_desktop" {
  name = "qemu-desktop"
}

resource "host_package_pacman" "libvirt" {
  name = "libvirt"
}

resource "host_package_pacman" "dmidecode" {
  name = "dmidecode"
}

resource "host_package_pacman" "virt_manager" {
  name = "virt-manager"
}

# libvirt's default NAT network uses dnsmasq for DHCP and nft-backed iptables
# rules for forwarding.
resource "host_package_pacman" "dnsmasq" {
  name = "dnsmasq"
}

resource "host_package_pacman" "iptables" {
  name = "iptables"
}

# Windows 11 needs UEFI firmware and a TPM 2.0 device. virt-manager configures
# the emulated TPM through swtpm when it is added to the guest.
resource "host_package_pacman" "edk2_ovmf" {
  name = "edk2-ovmf"
}

resource "host_package_pacman" "swtpm" {
  name = "swtpm"
}

# Reviewed 2026-07-31: the AUR package downloads Fedora's checksum-pinned,
# Microsoft-attestation-signed VirtIO driver ISO and installs it at
# /var/lib/libvirt/images/virtio-win.iso.
resource "host_package_aur" "virtio_win" {
  name = "virtio-win"

  depends_on = [
    host_package_pacman.libvirt,
  ]
}

# A repeatable Windows 11 domain specification and launcher. Stage the script
# before linking it so temporary Terraform worktrees can be safely retired.
resource "host_dir" "local_bin" {
  path = "~/.local/bin"
  mode = "0755"
}

resource "host_link" "windows11_vm_launcher" {
  source       = "libvirt/windows11-vm"
  destination  = "${host_dir.local_bin.path}/windows11-vm"
  stage_source = true

  depends_on = [
    host_package_aur.virtio_win,
    host_package_pacman.edk2_ovmf,
    host_package_pacman.qemu_desktop,
    host_package_pacman.swtpm,
    host_package_pacman.virt_manager,
  ]
}

# A repeatable Arch Linux installer VM and launcher. The guest uses native
# VirtIO devices, UEFI firmware, and the shared libvirt NAT network.
resource "host_link" "archlinux_vm_launcher" {
  source       = "libvirt/archlinux-vm"
  destination  = "${host_dir.local_bin.path}/archlinux-vm"
  stage_source = true

  depends_on = [
    host_package_pacman.edk2_ovmf,
    host_package_pacman.libvirt,
    host_package_pacman.qemu_desktop,
    host_package_pacman.swtpm,
    host_package_pacman.virt_manager,
  ]
}

resource "host_file_block" "local_bin_path" {
  block   = host_file.zshrc.blocks.path
  content = "export PATH=\"$HOME/.local/bin:$PATH\""
}

# AdGuard Home already owns port 53 on every host interface. Keep libvirt's
# dnsmasq instance for DHCP, but disable its DNS listener and advertise the
# AdGuard listener on virbr0 to guests.
resource "host_system_file" "libvirt_default_network" {
  source      = "${path.module}/libvirt/default-network.xml"
  destination = "/usr/local/share/terraform-libvirt-default-network.xml"

  mode              = "0644"
  adopt_existing    = true
  delete_on_destroy = false

  depends_on = [
    host_package_pacman.libvirt,
  ]
}

# Arch socket-activates the monolithic daemon and intentionally lets it exit
# after 120 idle seconds. Start and enable it initially, then ignore only the
# transient running flag so its normal idle exit does not create perpetual drift.
resource "host_systemd_service" "libvirtd" {
  name    = "libvirtd.service"
  enabled = true
  running = true

  depends_on = [
    host_package_pacman.dnsmasq,
    host_package_pacman.dmidecode,
    host_package_pacman.edk2_ovmf,
    host_package_pacman.iptables,
    host_package_pacman.qemu_desktop,
    host_package_pacman.swtpm,
  ]

  lifecycle {
    ignore_changes = [running]
  }
}

resource "host_system_file" "ensure_libvirt_default_network" {
  source      = "${path.module}/libvirt/ensure-default-network"
  destination = "/usr/local/bin/terraform-ensure-libvirt-default-network"

  mode              = "0755"
  adopt_existing    = true
  delete_on_destroy = true

  depends_on = [
    host_package_pacman.libvirt,
    host_system_file.libvirt_default_network,
  ]
}

resource "host_systemd_unit" "libvirt_default_network" {
  name = "terraform-libvirt-default-network.service"

  content = <<-EOT
    [Unit]
    Description=Ensure the Terraform-managed libvirt default network
    Requires=libvirtd.service
    After=libvirtd.service

    [Service]
    Type=oneshot
    ExecStart=/usr/local/bin/terraform-ensure-libvirt-default-network
    RemainAfterExit=yes

    [Install]
    WantedBy=multi-user.target
  EOT

  depends_on = [
    host_system_file.ensure_libvirt_default_network,
  ]
}

resource "host_systemd_service" "libvirt_default_network" {
  name    = host_systemd_unit.libvirt_default_network.name
  enabled = true
  running = true
  restart_trigger = sha256(jsonencode({
    network = filesha256("${path.module}/libvirt/default-network.xml")
    script  = filesha256("${path.module}/libvirt/ensure-default-network")
    unit    = host_systemd_unit.libvirt_default_network.content
  }))

  depends_on = [
    host_systemd_service.libvirtd,
    host_systemd_unit.libvirt_default_network,
  ]
}
