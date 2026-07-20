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

The VPN setup keeps secrets out of Terraform state. Its launchers fail closed
unless `/etc/openvpn/userlocked` and both input files have the expected
root-only ownership, type, and permissions.
