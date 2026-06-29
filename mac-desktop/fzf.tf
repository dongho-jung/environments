resource "host_package_brew" "fzf" {
  name = "fzf"
}

resource "host_file_block" "fzf_environment" {
  file_block = host_file.zshrc.block["environment"]
  priority   = 20
  content    = "export FZF_CTRL_R_OPTS=\"--scheme=history\""
}

resource "host_file_block" "fzf_plugin" {
  file_block = host_file.zshrc.block["plugins"]
  priority   = 10
  content    = "source <(fzf --zsh)"
}
