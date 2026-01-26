local vim = vim

-- Switch to ABC input on VimEnter
vim.api.nvim_create_autocmd("VimEnter", {
  callback = function()
    vim.fn.system("macism com.apple.keylayout.ABC")
  end,
})
