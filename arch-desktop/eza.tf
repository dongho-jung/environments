resource "host_package_pacman" "eza" {
  name = "eza"
}

resource "host_file_block" "eza_aliases" {
  block   = host_file.zshrc.blocks.alias
  content = "alias ls='eza' l='eza -lbF --git' ll='eza -la --git' tree='eza --tree --git' ltree='tree -l'"
}
