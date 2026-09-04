resource "host_package_pacman" "k9s" {
  name = "k9s"
}

resource "host_file" "k9s_solarized_light_skin" {
  path    = "~/.config/k9s/skins/solarized-light.yaml"
  content = file("${path.module}/k9s/skins/solarized-light.yaml")

  depends_on = [
    host_package_pacman.k9s,
  ]
}

resource "host_file_block" "k9s_skin_environment" {
  block   = host_file.zshrc.blocks.environment
  content = "export K9S_SKIN=solarized-light"

  depends_on = [
    host_file.k9s_solarized_light_skin,
  ]
}
