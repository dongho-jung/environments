resource "host_package_brew" "eza" {
  name = "eza"
}

resource "host_file_block" "eza_aliases" {
  file_block = host_file.zshrc.block["alias"]
  priority   = 40
  content    = "alias ls='eza' l='eza -lbF --git' ll='eza -la --git' tree='eza --tree --git' ltree='tree -l'"
}
