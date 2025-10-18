local vim = vim
local Plug = vim.fn['plug#']

vim.call('plug#begin')
Plug('github/copilot.vim')
Plug('ericbn/vim-solarized')
Plug('mhinz/vim-startify')
Plug('keaising/im-select.nvim')
vim.call('plug#end')

vim.g.mapleader = ' '
vim.keymap.set('n', '<leader>e', vim.diagnostic.open_float, { noremap = true, silent = true })
vim.keymap.set('n', '[d', vim.diagnostic.goto_prev, { noremap = true, silent = true })
vim.keymap.set('n', ']d', vim.diagnostic.goto_next, { noremap = true, silent = true })

vim.cmd('syntax enable')
vim.opt.background = 'light'
vim.cmd('colorscheme solarized')

vim.opt.autoindent = true
vim.opt.expandtab = true
vim.opt.mouse = 'a'
vim.opt.number = true
vim.opt.shiftwidth = 4
vim.opt.softtabstop = 4
vim.opt.tabstop = 4

vim.g.copilot_filetypes = {
  markdown = false,
  python = true,
}
vim.keymap.set("i", "<C-,>", "<Plug>(copilot-previous)", { silent = true, desc = "Copilot Previous" })
vim.keymap.set("i", "<C-.>", "<Plug>(copilot-next)", { silent = true, desc = "Copilot Next" })

require('im_select').setup {}

local opts = { noremap = true, silent = true }

-- Normal mode: line / word navigation
vim.keymap.set('n', '<C-a>', '^', opts)
vim.keymap.set('n', '<C-e>', '$', opts)
vim.keymap.set('n', '<M-b>', 'b', opts)
vim.keymap.set('n', '<M-f>', 'w', opts)

-- Insert mode: line / word navigation
vim.keymap.set('i', '<C-a>', '<C-o>^', opts)
vim.keymap.set('i', '<C-e>', '<C-o>$', opts)
vim.keymap.set('i', '<M-b>', '<C-o>b', opts)
vim.keymap.set('i', '<M-f>', '<C-o>w', opts)

-- Ctrl + Up/Down → move to top/bottom of screen
vim.keymap.set('n', '<C-Up>', 'H', opts)
vim.keymap.set('n', '<C-Down>', 'L', opts)
vim.keymap.set('i', '<C-Up>', '<C-o>H', opts)
vim.keymap.set('i', '<C-Down>', '<C-o>L', opts)

-- Alt + Up/Down → jump to previous/next blank line
vim.keymap.set('n', '<M-Up>', '{', opts)
vim.keymap.set('n', '<M-Down>', '}', opts)
vim.keymap.set('i', '<M-Up>', '<C-o>{', opts)
vim.keymap.set('i', '<M-Down>', '<C-o>}', opts)
