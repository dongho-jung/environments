# nftables arrived as a dependency of another package; declaring it marks it
# explicit so it survives even if the dependent package goes away.
#
# The service is intentionally NOT enabled: /etc/nftables.conf is still the
# stock ruleset, and enabling a default-deny firewall blindly could cut off
# AdGuard Home DNS for LAN clients. Write a ruleset first (host_file +
# host_systemd_service) when actually turning the firewall on.
resource "host_package_pacman" "nftables" {
  name = "nftables"
}
