local WEZTERM_BIN   = "/opt/homebrew/bin/wezterm"
local STORE_KEY     = "wez_dropdown_win_id"
local WORKSPACE     = "dropdown"

local spaces        = require("hs.spaces")
local window        = require("hs.window")
local screen        = require("hs.screen")
local wfilt         = require("hs.window.filter")

local HEIGHT_RATIO  = 0.45
local MARGIN_TOP    = 0
local SLIDE_SECS    = 0.12
window.animationDuration = SLIDE_SECS

local function screen_for_action()
  return hs.mouse.getCurrentScreen() or screen.mainScreen()
end

local function active_space_for_screen(scr)
  if spaces.screensHaveSeparateSpaces() then
    local act = spaces.activeSpaces() or {}
    return act[scr:getUUID()] or spaces.focusedSpace()
  else
    return spaces.focusedSpace()
  end
end

local function target_frame(scr)
  local f = scr:frame()
  local h = math.floor(f.h * HEIGHT_RATIO)
  return { x = f.x, y = f.y + MARGIN_TOP, w = f.w, h = h }
end

local function hidden_frame(scr)
  local tf = target_frame(scr)
  return { x = tf.x, y = (tf.y - tf.h) - 20, w = tf.w, h = tf.h }
end

local function get_saved_win_id()  return hs.settings.get(STORE_KEY) end
local function save_win_id(id)     if id then hs.settings.set(STORE_KEY, id) end end
local function clear_saved_win()   hs.settings.clear(STORE_KEY) end

local function find_window_any_space_by_id(winid)
  local f = wfilt.new()
  f:setDefaultFilter({})
  f:setCurrentSpace(false)
  for _, w in ipairs(f:getWindows()) do
    if w:id() == winid then return w end
  end
  return nil
end

local function get_saved_win()
  local id = get_saved_win_id()
  if not id then return nil end
  local w = window.get(id)
  if w then return w end
  w = find_window_any_space_by_id(id)
  if w then return w end
  clear_saved_win()
  return nil
end

local function window_primary_space(w)
  local ws = spaces.windowSpaces(w) or {}
  if #ws > 0 then return ws[1] end
  return nil
end

local function goto_space(sid)
  if not sid then return false end
  local ok = false
  if type(spaces.gotoSpace) == "function" then
    ok = not (spaces.gotoSpace(sid) == false)
  elseif type(spaces.focusSpace) == "function" then
    ok = not (spaces.focusSpace(sid) == false)
  else
    ok = false
  end
  if ok then hs.timer.usleep(250000) end
  return ok
end

local function jump_to_window_space_or_fallback(w)
  local wid = window_primary_space(w)
  local curr = spaces.focusedSpace()
  if wid and curr ~= wid then
    return goto_space(wid)
  end
  return true
end

local function focus_win(w)
  if not w then return false end
  local app = w:application()
  if app then app:activate(true) end
  w:raise(); w:focus()
  return true
end

local function slide_down(w)
  if not w then return end

  if w:isMinimized() then
    w:unminimize()
    hs.timer.usleep(200000)
  end

  jump_to_window_space_or_fallback(w)

  local scr = w:screen() or screen_for_action()

  local old = window.animationDuration
  window.animationDuration = 0
  w:move(hidden_frame(scr), scr)
  window.animationDuration = old

  w:move(target_frame(scr), scr, SLIDE_SECS)
  focus_win(w)
end

local function hide_dropdown(w)
  if w and not w:isMinimized() then w:minimize() end
end

local function start_and_capture_id()
  local before = {}
  for _, win in ipairs(window.allWindows()) do before[win:id()] = true end

  local task = hs.task.new(WEZTERM_BIN, nil, { "start", "--always-new-process", "--workspace", WORKSPACE })
  task:start()

  local t0 = hs.timer.secondsSinceEpoch()
  local poll
  poll = hs.timer.doEvery(0.15, function()
    local spawned_pid = task:pid()
    local candidate, newwins = nil, {}

    for _, win in ipairs(window.allWindows()) do
      local wid = win:id()
      if not before[wid] then
        table.insert(newwins, win)
        local app = win:application()
        if spawned_pid and app and app:pid() == spawned_pid then
          candidate = win; break
        end
      end
    end

    if not candidate and #newwins == 1 then candidate = newwins[1] end

    if candidate then
      save_win_id(candidate:id())
      slide_down(candidate)
      poll:stop(); return
    end

    if hs.timer.secondsSinceEpoch() - t0 > 7 then
      poll:stop(); hs.alert.show("Failed to start wezterm dropdown")
    end
  end)
end

hs.hotkey.bind({ "cmd" }, "`", function()
  local w = get_saved_win()
  if w then
    local front = window.frontmostWindow()
    if front and front:id() == w:id() then
      hide_dropdown(w)
    else
      slide_down(w)
    end
  else
    start_and_capture_id()
  end
end)

