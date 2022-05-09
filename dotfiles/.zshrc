export ZSH="$HOME/.oh-my-zsh"
ZSH_THEME="random"
ZSH_THEME_RANDOM_QUIET=true

plugins=(docker emotty fzf git z)

zstyle ':completion:*:*:-command-:*:*' ignored-patterns '_*'       


source $ZSH/oh-my-zsh.sh

HISTSIZE=10000
SAVEHIST=1000000

setopt share_history

alias "open=xdg-open"
alias "y=xclip -selection clipboard"
alias "p=xclip -selection clipboard -o"

EDITOR=vi
PATH=$PATH:/usr/share/bcc/tools:~/projects/scripts
