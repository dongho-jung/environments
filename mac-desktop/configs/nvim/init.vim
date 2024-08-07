call plug#begin()
Plug 'ericbn/vim-solarized'
Plug 'mhinz/vim-startify'
Plug 'brglng/vim-im-select'
call plug#end()

syntax enable
set background=light
colorscheme solarized

set autoindent
set expandtab
set mouse=a
set number
set shiftwidth=4
set softtabstop=4
set tabstop=4

let g:im_select_enable_cmd_line = 0
