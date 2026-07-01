local augroup = vim.api.nvim_create_augroup("myGroup", { clear = true })

vim.api.nvim_create_autocmd("BufWritePre", {
    group = augroup,
    pattern = { "*.tf", "*.tfvars" },
    callback = function(event)
        vim.lsp.buf.format({ async = false, bufnr = event.buf })
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
