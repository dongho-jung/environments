# Arch desktop environment

This configuration assumes a minimal host bootstrap has already created the
`dongho` user and installed/configured `sudo`. Terraform must run as `dongho`,
not as root.

## First apply on a new host

1. Create `dongho`, add it to `wheel`, install `sudo`, and enable wheel sudo
   access outside Terraform. The declared `host_user` and `sudo` package then
   maintain that bootstrap state.
2. Initialize Terraform and create the SSH resources before cloning the private
   shell-history repository:

   ```sh
   install -d -m 0700 ~/.local/state/terraform/arch-desktop
   terraform init
   sudo -v
   terraform apply \
     -target=host_ssh_key.github \
     -target=host_file.github_known_hosts \
     -target=host_ssh_config_host.github
   ```

Terraform state lives at
`~/.local/state/terraform/arch-desktop/terraform.tfstate`. The fixed local
backend keeps the canonical checkout and temporary Git worktrees on the same
locked state instead of silently creating independent host inventories.

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
software TPM 2.0 support, NAT networking, the Windows VirtIO driver ISO, and the
`windows11-vm` launcher. Download a Windows 11 x64 ISO to `~/Downloads`, then
create or start the VM and open its graphical console with one command:

```sh
windows11-vm
```

On first use, the launcher selects the newest `*Win*11*x64*.iso` in
`~/Downloads` and creates `win11` with 4 vCPUs, 8 GiB RAM, a 128 GiB sparse
disk, Q35, UEFI, SPICE, and exactly one emulated CRB TPM. Later invocations
start the existing domain when necessary and open its console. Set
`WINDOWS11_ISO=/path/to/windows.iso` to override ISO discovery, or run
`windows11-vm --print-xml` to inspect the domain specification without creating
it.

The system disk and initial network adapter use Windows-supported emulated
devices so Setup does not require drivers. The launcher also attaches
`/var/lib/libvirt/images/virtio-win.iso`; run `virtio-win-guest-tools.exe` from
that CD in Windows after installation to add the optimized drivers and guest
agent. The Windows 11 OS profile supplies the TPM automatically, so do not add a
second TPM in virt-manager.

After the first Terraform apply, sign out and back in once if the new `libvirt`
group membership is not yet visible to the desktop session. `SUPER+M` exits
Hyprland; logging in again on tty1 is sufficient, so a full reboot is not
required.

Terraform defines, starts, and enables autostart for the `default` NAT network.
Its DHCP service advertises AdGuard Home at `192.168.122.1` for DNS, avoiding a
second port 53 listener.

Keep the SPICE display and video devices that virt-manager proposes for the
graphical console. GPU passthrough is a separate setup and is not enabled here.
