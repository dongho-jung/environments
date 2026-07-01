local capabilities = vim.lsp.protocol.make_client_capabilities()
local cmp_ok, cmp_nvim_lsp = pcall(require, "cmp_nvim_lsp")

if cmp_ok then
    capabilities = cmp_nvim_lsp.default_capabilities(capabilities)
end

vim.lsp.config("terraformls", {
    cmd = { "terraform-ls", "serve" },
    filetypes = { "terraform", "terraform-vars" },
    root_markers = { ".terraform", ".git" },
    capabilities = capabilities,
})

vim.lsp.enable("terraformls")

vim.diagnostic.config({
    virtual_text = true,
    signs = true,
    underline = true,
    update_in_insert = false,
})
