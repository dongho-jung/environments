local vim = vim
local Plug = vim.fn['plug#']

vim.call('plug#begin')
Plug('github/copilot.vim')
Plug('ericbn/vim-solarized')
Plug('mhinz/vim-startify')
vim.call('plug#end')

-- Copilot settings
vim.g.copilot_filetypes = {
  markdown = false,
  python = true,
}
vim.keymap.set("i", "<C-,>", "<Plug>(copilot-previous)", { silent = true, desc = "Copilot Previous" })
vim.keymap.set("i", "<C-.>", "<Plug>(copilot-next)", { silent = true, desc = "Copilot Next" })
