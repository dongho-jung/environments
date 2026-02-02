local vim = vim
local Plug = vim.fn['plug#']

vim.call('plug#begin')
Plug('ericbn/vim-solarized')
Plug('mhinz/vim-startify')
Plug('keaising/im-select.nvim')
Plug('m4xshen/hardtime.nvim')
Plug('folke/which-key.nvim')
vim.call('plug#end')

vim.cmd('syntax enable')
vim.cmd('colorscheme solarized')

vim.opt.background = 'light'
vim.opt.autoindent = true
vim.opt.expandtab = true
vim.opt.mouse = 'a'
vim.opt.number = true
vim.opt.relativenumber = true
vim.opt.shiftwidth = 4
vim.opt.softtabstop = 4
vim.opt.tabstop = 4
vim.opt.showcmd = true
vim.opt.showcmdloc = "statusline"
vim.opt.statusline = "%S %f %=%l:%c"
vim.opt.clipboard = "unnamedplus"

require('im_select').setup({})
require('hardtime').setup({
    disabled_keys = {
        ["<Up>"]    = false,
        ["<Down>"]  = false,
        ["<Left>"]  = false,
        ["<Right>"] = false,
    },

    restricted_keys = {
        ["<Up>"]    = { "n", "x" },
        ["<Down>"]  = { "n", "x" },
        ["<Left>"]  = { "n", "x" },
        ["<Right>"] = { "n", "x" },
    },
})
require('which-key').setup({
    icons = {
        mappings = false,
    },
})

local augroup = vim.api.nvim_create_augroup("RelNumToggle", { clear = true })

vim.api.nvim_create_autocmd("InsertEnter", {
	group = augroup,
	callback = function()
		vim.opt.relativenumber = false
	end,
})

vim.api.nvim_create_autocmd("InsertLeave", {
	group = augroup,
	callback = function()
		vim.opt.relativenumber = true
	end,
})

vim.api.nvim_create_autocmd("VimEnter", {
	callback = function()
		vim.fn.system("macism com.apple.keylayout.ABC")
	end,
})

vim.api.nvim_create_autocmd("InsertEnter", {
	group = augroup,
	callback = function()
		vim.opt.relativenumber = false
	end,
})

vim.api.nvim_create_autocmd("InsertLeave", {
	group = augroup,
	callback = function()
		vim.opt.relativenumber = true
	end,
})
