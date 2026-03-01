local wezterm = require 'wezterm';
local config = wezterm.config_builder();
local act = wezterm.action
local DROPDOWN_WS = "dropdown"

config.color_scheme = 'Solarized Light (Gogh)'
config.window_decorations = 'RESIZE'
config.harfbuzz_features = { "calt=0", "clig=0", "liga=0" }
config.adjust_window_size_when_changing_font_size = false

wezterm.on("window-created", function(window, pane)
  window:perform_action(act.SetWindowLevel("AlwaysOnTop"), pane)

  wezterm.sleep_ms(200)
  window:perform_action(act.SetWindowLevel("Normal"), pane)
end)

wezterm.on("window-focus-changed", function(window, pane)
  if window:active_workspace() == DROPDOWN_WS then
    window:perform_action(act.SetWindowLevel("AlwaysOnTop"), pane)
  else
    window:perform_action(act.SetWindowLevel("Normal"), pane)
  end
end)

wezterm.on("window-config-reloaded", function(window, pane)
  if window:active_workspace() == DROPDOWN_WS then
    window:perform_action(act.SetWindowLevel("AlwaysOnTop"), pane)
  end
end)

wezterm.on('format-window-title', function(tab, pane, tabs, panes, config)
  local workspace = wezterm.mux.get_active_workspace()
  return workspace or "wezterm"
end)

local zoomed = false
local original_font_size = null

wezterm.on("toggle_font_zoom", function(window, _)
  local overrides = window:get_config_overrides() or {}
  local current_config = window:effective_config()
  local current_font_size = current_config.font_size

  if zoomed then
    if original_font_size then
      overrides.font_size = original_font_size
    else
      overrides.font_size = current_font_size / 2
    end
    zoomed = false
  else
    original_font_size = current_font_size
    overrides.font_size = current_font_size * 2
    zoomed = true
  end

  window:set_config_overrides(overrides)
end)

config.keys = {
    {
        key = "=",
        mods = "ALT",
        action = wezterm.action.EmitEvent("toggle_font_zoom"),
    },
    {
        key = "n",
        mods = "CMD",
        action = wezterm.action_callback(function(window, pane)
          if window:active_workspace() == DROPDOWN_WS then
            wezterm.background_child_process {
              '/opt/homebrew/bin/wezterm', 'start', '--workspace', 'default', '--cwd', '~'
            }
            window:perform_action(act.SetWindowLevel 'Normal', pane)
          else
            window:perform_action(act.SpawnWindow, pane)
            window:perform_action(act.SetWindowLevel 'AlwaysOnTop', pane)
          end
        end),
    },
}

return config;
