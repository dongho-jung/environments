local vim = vim
local Plug = vim.fn['plug#']

vim.call('plug#begin')
Plug('github/copilot.vim')
Plug('ericbn/vim-solarized')
Plug('mhinz/vim-startify')
Plug('keaising/im-select.nvim')
vim.call('plug#end')

-- Copilot settings
vim.g.copilot_filetypes = {
  markdown = false,
  python = true,
}
vim.keymap.set("i", "<C-,>", "<Plug>(copilot-previous)", { silent = true, desc = "Copilot Previous" })
vim.keymap.set("i", "<C-.>", "<Plug>(copilot-next)", { silent = true, desc = "Copilot Next" })

-- im-select setup (safe load)
local ok, im_select = pcall(require, 'im_select')
if ok then
  im_select.setup {}
end
