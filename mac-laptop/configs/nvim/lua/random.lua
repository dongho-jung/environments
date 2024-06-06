local M = {}

function M.set_random_colorscheme()
  local function try_set_colorscheme()
    math.randomseed(os.time())
    local colorschemes = vim.fn.getcompletion("", "color")
    local random_index = math.random(1, #colorschemes)
    local success, _ = pcall(vim.cmd, "colorscheme " .. colorschemes[random_index])
    return success
  end

  local max_attempts = 3
  for _ = 1, max_attempts do
    if try_set_colorscheme() then return end
  end
end

return M
