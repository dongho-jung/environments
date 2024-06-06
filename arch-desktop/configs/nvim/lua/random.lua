local M = {}

function M.set_random_colorscheme()
  math.randomseed(os.time())
  local colorschemes = vim.fn.getcompletion("", "color")
  local random_index = math.random(1, #colorschemes)
  vim.cmd("colorscheme " .. colorschemes[random_index])
end

return M
