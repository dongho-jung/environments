#!/bin/bash

entries=(
    dotfiles:"$HOME/.zshrc":zshrc
    dotfiles:"$HOME/.vimrc":vimrc
)

for entry in "${entries[@]}"
do
    IFS=: read category path name <<<"$entry"
    mkdir -p ./$category

    if [ -d $path ]; then
        cp -r $path/. ./$category/$name
    else
        cp -r $path ./$category/$name
    fi
done

git status
git --no-pager diff
