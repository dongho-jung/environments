#!/bin/bash

entries=(
    dotfiles:"$HOME/.zshrc":zshrc
    dotfiles:"$HOME/.vimrc":vimrc
    dotfiles:"$HOME/.gitconfig":gitconfig
    configs:"$HOME/.config/i3/config":i3
    configs:"$HOME/.config/i3status/config":i3status
    configs:"$HOME/.config/flameshot/flameshot.ini":flameshot
    spool:"/var/spool/cron/$(whoami)":cron  # might need `chmod o+rx /var/spool/cron`
    directories:"$HOME/.uim.d":uim
    services:"/etc/systemd/system/init-keycode.service":init-keycode.service
)

for entry in "${entries[@]}"
do
    IFS=: read category path name <<< $entry
    mkdir -p ./$category

    if [ -d $path ]; then
        cp -r $path/. ./$category/$name
    else
        cp -r $path ./$category/$name
    fi
done

git status
git --no-pager diff
