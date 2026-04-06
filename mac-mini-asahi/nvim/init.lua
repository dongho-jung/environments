vim.g.clipboard = {
  name = "wl-clipboard",
  copy = {
    ["+"] = "wl-copy",
    ["*"] = "wl-copy",
  },
  paste = {
    ["+"] = "wl-paste",
    ["*"] = "wl-paste",
  },
  cache_enabled = 0,
}

vim.opt.clipboard = "unnamedplus"
vim.opt.number = true

vim.opt.termguicolors = true
vim.opt.background = "light"
require("theme").setup()
