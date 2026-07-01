resource "host_file" "gitconfig" {
  path = "~/.gitconfig"

  content = <<-EOT
    [user]
      email = dongho971220@gmail.com
      name = dongho-jung
    [core]
      editor = vim
      autocrlf = input
      quotePath = false
      hooksPath = /Users/dongho/.git-hooks
    [commit]
      verbose = true
    [init]
      defaultBranch = main
    [pull]
      rebase = false
    [push]
      autoSetupRemote = true
  EOT
}

resource "host_file_block" "git_aliases" {
  block = host_file.zshrc.blocks.alias

  content = <<-EOT
    alias ga='git add' gc='git commit -v' gl='git pull' gp='git push' gg='lazygit' gst='git status' gco='git checkout'
    alias gr='git restore' grs='git restore --staged' gd='git diff' gds='git diff --staged' glog='git log --all --decorate --oneline --graph'
  EOT
}
