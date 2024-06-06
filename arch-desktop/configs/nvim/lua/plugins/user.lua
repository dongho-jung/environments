-- You can also add or configure plugins by creating files in this `plugins/` folder
-- Here are some examples:

---@type LazySpec
return {
  "lilydjwg/fcitx.vim",
  {
    "zbirenbaum/copilot.lua",
    opts = {
      filetypes = {
        markdown = false,
        [""] = false,
      },
    },
  },
  config = function()
    vim.cmd [[
      command! DiffOrig vert new | set buftype=nofile | read ++edit # | 0d_
      \ | diffthis | wincmd p | diffthis
    ]]
  end,
}
