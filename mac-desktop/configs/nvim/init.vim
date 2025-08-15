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

imap <silent><script><expr> <C-E> copilot#Accept("<End>")
let g:copilot_no_tab_map = v:true
let g:copilot_assume_mapped = v:true
let g:copilot_filetypes = {
      \ 'markdown': v:false,
      \ 'python': v:true,
      \ }
