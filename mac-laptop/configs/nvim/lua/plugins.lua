local vim = vim
local Plug = vim.fn['plug#']

vim.call('plug#begin')
Plug 'ericbn/vim-solarized'
Plug 'mhinz/vim-startify'
Plug 'm4xshen/hardtime.nvim'
vim.call('plug#end')

require("hardtime").setup()
