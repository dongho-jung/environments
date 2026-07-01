resource "host_package_brew" "fzf" {
  name = "fzf"
}

resource "host_file_block" "fzf_environment" {
  block   = host_file.zshrc.blocks.environment
  content = "export FZF_CTRL_R_OPTS=\"--scheme=history\""
}

resource "host_file_block" "fzf_plugin" {
  block   = host_file.zshrc.blocks.plugins
  content = "source <(fzf --zsh)"
}
