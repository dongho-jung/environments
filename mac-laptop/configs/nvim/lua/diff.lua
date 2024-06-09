local M = {}

function attach_mappings(_, map)
  map("i", "<CR>", function(prompt_bufnr)
    local action_state = require "telescope.actions.state"
    local actions = require "telescope.actions"
    local selected_entry = action_state.get_selected_entry()
    local filename = selected_entry.path
    actions.close(prompt_bufnr)
    vim.cmd("vsplit " .. filename)
    vim.cmd "windo diffthis"
    vim.cmd "windo set scrollbind"
    vim.cmd "windo normal! zR"
  end)
  return true
end

function M.diff_old_files()
  require("telescope.builtin").oldfiles {
    attach_mappings = attach_mappings,
  }
end

function M.diff_find_files()
  require("telescope.builtin").find_files {
    find_command = { "fd", "--type", "f" },
    attach_mappings = attach_mappings,
  }
end

return M
