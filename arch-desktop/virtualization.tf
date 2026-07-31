# QEMU/KVM desktop stack. qemu-desktop includes the SPICE, GTK, PipeWire and
# VirtIO display pieces used by virt-manager's graphical console.
resource "host_package_pacman" "qemu_desktop" {
  name = "qemu-desktop"
}

resource "host_package_pacman" "libvirt" {
  name = "libvirt"
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
    host_aur_helper.yay,
    host_package_pacman.libvirt,
  ]
}

# AdGuard Home already owns port 53 on every host interface. Keep libvirt's
# dnsmasq instance for DHCP, but disable its DNS listener and advertise the
# AdGuard listener on virbr0 to guests.
resource "host_system_file" "libvirt_default_network" {
  source      = "${path.module}/libvirt/default-network.xml"
  destination = "/etc/libvirt/qemu/networks/default.xml"

  mode              = "0600"
  adopt_existing    = true
  delete_on_destroy = false

  depends_on = [
    host_package_pacman.libvirt,
  ]
}

# The monolithic daemon remains the supported Arch setup and also permits
# domains marked for autostart to start with the host.
resource "host_systemd_service" "libvirtd" {
  name    = "libvirtd.service"
  enabled = true
  running = true

  depends_on = [
    host_package_pacman.dnsmasq,
    host_package_pacman.edk2_ovmf,
    host_package_pacman.iptables,
    host_package_pacman.qemu_desktop,
    host_package_pacman.swtpm,
    host_system_file.libvirt_default_network,
  ]
}
