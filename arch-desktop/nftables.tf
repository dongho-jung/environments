# Forget the old package-only declaration without uninstalling nftables.
# Owning a package while intentionally managing neither rules nor the service
# implied firewall coverage that this configuration did not actually provide.
removed {
  from = host_package_pacman.nftables

  lifecycle {
    destroy = false
  }
}
