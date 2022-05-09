#!/bin/bash

entries=(
	dotfiles:"$HOME/.zshrc"
	dotfiles:"$HOME/.vimrc"
	dotfiles:"$HOME/.gitconfig"
	configs:"$HOME/.config/i3/config":i3
	configs:"$HOME/.config/i3status/config":i3status
	configs:"$HOME/.config/i3status/config":flameshot
)

for entry in "${entries[@]}"
do
	IFS=: read category path name <<< $entry

	if [ -z "$name" ]
	then
		ln -f $path ./${category}
	else
		ln -f $path ./${category}/${name}
	fi	
done
