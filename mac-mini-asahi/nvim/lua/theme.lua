local M = {}

function M.setup()
  vim.opt.termguicolors = true
  vim.opt.background = "light"

  -- Solarized Light palette
  local colors = {
    base03  = "#002b36",
    base02  = "#073642",
    base01  = "#586e75",
    base00  = "#657b83",
    base0   = "#839496",
    base1   = "#93a1a1",
    base2   = "#eee8d5",
    base3   = "#fdf6e3",
    yellow  = "#b58900",
    orange  = "#cb4b16",
    red     = "#dc322f",
    magenta = "#d33682",
    violet  = "#6c71c4",
    blue    = "#268bd2",
    cyan    = "#2aa198",
    green   = "#859900",
  }

  local set = vim.api.nvim_set_hl

  set(0, "Normal",       { fg = colors.base00, bg = colors.base3 })
  set(0, "NormalFloat",  { fg = colors.base00, bg = colors.base3 })
  set(0, "EndOfBuffer",  { fg = colors.base3,  bg = colors.base3 })
  set(0, "SignColumn",   { bg = colors.base3 })

  set(0, "CursorLine",   { bg = colors.base2 })
  set(0, "CursorLineNr", { fg = colors.orange, bold = true })

  set(0, "StatusLine",   { fg = colors.base1, bg = colors.base2 })
  set(0, "StatusLineNC", { fg = colors.base0, bg = colors.base2 })

  set(0, "Comment",      { fg = colors.base1, italic = true })
  set(0, "Keyword",      { fg = colors.green })
  set(0, "Function",     { fg = colors.blue })
  set(0, "String",       { fg = colors.cyan })
  set(0, "Identifier",   { fg = colors.base00 })
  set(0, "Type",         { fg = colors.yellow })
  set(0, "Constant",     { fg = colors.magenta })
  set(0, "Number",       { fg = colors.magenta })
  set(0, "Error",        { fg = colors.red, bold = true })
end

return M
