resource "host_package_aur" "onepassword_cli" {
  name = "1password-cli"

  depends_on = [
    host_aur_helper.yay,
  ]
}
