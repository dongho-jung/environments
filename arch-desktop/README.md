# Arch desktop environment

This configuration assumes a minimal host bootstrap has already created the
`dongho` user and installed/configured `sudo`. Terraform must run as `dongho`,
not as root; `host_aur_helper` intentionally refuses to run `makepkg` as root.

## First apply on a new host

1. Create `dongho`, add it to `wheel`, install `sudo`, and enable wheel sudo
   access outside Terraform. The declared `host_user` and `sudo` package then
   maintain that bootstrap state.
2. Initialize Terraform and create the SSH resources before cloning the private
   shell-history repository:

   ```sh
   terraform init
   sudo -v
   terraform apply \
     -target=host_ssh_key.github \
     -target=host_file.github_known_hosts \
     -target=host_ssh_config_host.github
   ```

3. Register `~/.ssh/id_ed25519.pub` with the `dongho-jung` GitHub account, then
   run the normal full apply:

   ```sh
   sudo -v
   terraform apply
   ```

4. Place `profile-userlocked.ovpn` in `~/Downloads` and create the root-only VPN
   profile and secrets:

   ```sh
   sudo bash openvpn/setup-root.sh
   sudo -n /usr/local/bin/vpn-up
   ```

   Existing installations using `/etc/openvpn/client` are migrated automatically.
   For a migration that must not prompt for new secrets, use
   `sudo bash openvpn/setup-root.sh --non-interactive`.

The VPN setup keeps secrets out of Terraform state. Its launchers fail closed
unless `/etc/openvpn/userlocked` and both input files have the expected
root-only ownership, type, and permissions.

## Windows 11 virtual machine

The configuration installs QEMU/KVM, libvirt, virt-manager, UEFI firmware,
software TPM 2.0 support, NAT networking, and the Windows VirtIO driver ISO.
After the first apply:

1. Sign out and back in once so the new `libvirt` group membership is visible
   to the desktop session.
2. Open `virt-manager` and use the `QEMU/KVM` system connection.
3. Open **Edit > Connection Details > Virtual Networks**, select `default`,
   enable **Autostart**, and start the network. Its DHCP service advertises
   AdGuard Home at `192.168.122.1` for DNS, avoiding a second port 53 listener.
4. Create a VM from a Windows 11 ISO and select **Customize configuration before
   install**. Use a Q35 chipset, x86_64 UEFI firmware, a `host-passthrough` CPU,
   and an emulated CRB TPM 2.0 device.
5. Attach `/var/lib/libvirt/images/virtio-win.iso` as a SATA CD-ROM. If the
   installer cannot see a VirtIO disk, load the matching Windows 11 AMD64
   storage driver from that ISO. Run `virtio-win-guest-tools.exe` in Windows
   after installation to install the remaining VirtIO drivers and guest agent.

Keep the SPICE display and video devices that virt-manager proposes for the
graphical console. GPU passthrough is a separate setup and is not enabled here.
