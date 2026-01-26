local vim = vim
local opts = { noremap = true, silent = true }

-- Diagnostic keymaps
vim.keymap.set('n', '<leader>e', vim.diagnostic.open_float, opts)
vim.keymap.set('n', '[d', vim.diagnostic.goto_prev, opts)
vim.keymap.set('n', ']d', vim.diagnostic.goto_next, opts)

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

-- Ctrl + Up/Down: move to top/bottom of screen
vim.keymap.set('n', '<C-Up>', 'H', opts)
vim.keymap.set('n', '<C-Down>', 'L', opts)
vim.keymap.set('i', '<C-Up>', '<C-o>H', opts)
vim.keymap.set('i', '<C-Down>', '<C-o>L', opts)

-- Alt + Up/Down: jump to previous/next blank line
vim.keymap.set('n', '<M-Up>', '{', opts)
vim.keymap.set('n', '<M-Down>', '}', opts)
vim.keymap.set('i', '<M-Up>', '<C-o>{', opts)
vim.keymap.set('i', '<M-Down>', '<C-o>}', opts)
