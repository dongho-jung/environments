resource "host_package_pacman" "starship" {
  name = "starship"
}

resource "host_file" "starship_config" {
  path = "~/.config/starship.toml"

  content = <<-EOT
    [aws]
    disabled = true
  EOT
}

resource "host_file_block" "starship_init" {
  block   = host_file.zshrc.blocks.init
  content = "eval \"$(starship init zsh)\""
}
