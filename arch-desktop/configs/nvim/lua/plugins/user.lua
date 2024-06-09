-- You can also add or configure plugins by creating files in this `plugins/` folder
-- Here are some examples:

---@type LazySpec
return {
  {
    "zbirenbaum/copilot.lua",
    opts = {
      filetypes = {
        markdown = false,
        [""] = false,
      },
    },
  },
  {
    "goolord/alpha-nvim",
    enabled = false,
  },
  {
    "charludo/projectmgr.nvim",
    lazy = false, -- important!
    opts = {
      session = {
        enabled = false,
      },
    },
  },
  {
    "keaising/im-select.nvim",
    opts = {
      default_im_select = "keyboard-us",
      set_default_events = { "VimEnter", "FocusGained", "InsertLeave", "CmdlineLeave" },
      set_previous_events = { "InsertEnter", "CmdlineEnter" },
    },
  },
  "dongho-jung/telescope-autojump.nvim",
}
