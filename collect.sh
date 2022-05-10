#!/bin/bash

entries=(
    dotfiles:"$HOME/.zshrc":zshrc
    dotfiles:"$HOME/.vimrc":vimrc
    dotfiles:"$HOME/.gitconfig":gitconfig
    configs:"$HOME/.config/i3/config":i3
    configs:"$HOME/.config/i3status/config":i3status
    configs:"$HOME/.config/flameshot/flameshot.ini":flameshot
    spool:"/var/spool/cron/$(whoami)":cron  # might need `chmod o+rx /var/spool/cron`
)

for entry in "${entries[@]}"
do
    IFS=: read category path name <<< $entry
    cp $path ./${category}/${name}
done
