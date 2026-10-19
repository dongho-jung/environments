local english = "com.apple.keylayout.ABC"
local korean = "com.apple.inputmethod.Korean.2SetKorean"
local japanese = "com.apple.inputmethod.Kotoeri.RomajiTyping.Japanese"
local setting = "inputSwitch.lastAsianSource"

local function isAsian(source)
  return source == korean or source == japanese
end

local lastAsian = hs.settings.get(setting)
if not isAsian(lastAsian) then lastAsian = korean end
local target, timer, waiting, stepSource
local steps, limit = 0, 0
local bindings = {}

local function rememberCurrent()
  local current = hs.keycodes.currentSourceID()
  if isAsian(current) then
    lastAsian = current
    hs.settings.set(setting, current)
  end
  return current
end

local function cancel()
  if timer then timer:stop(); timer = nil end
  target, waiting = nil, false
end

local function finish()
  cancel()
  rememberCurrent()
end

local function failed()
  cancel()
  hs.alert.show("Input source switch failed. Check Keyboard > Keyboard Shortcuts > Input Sources")
end

local function advance()
  local current = hs.keycodes.currentSourceID()
  if current == target then finish(); return end
  local shortcut = hs.hotkey.systemAssigned({"ctrl", "alt"}, "space")
  if not shortcut or not shortcut.enabled then failed(); return end
  if steps >= limit then failed(); return end
  steps = steps + 1
  waiting, stepSource = true, current
  timer = hs.timer.doAfter(1, failed)
  -- TISSelectInputSource can change the menu without activating a CJK IME.
  -- The native shortcut switches the focused app's actual input method.
  -- The switcher needs real modifier press/release events. keyStroke only
  -- attaches flags to Space and can leave the native shortcut unhandled.
  local event = hs.eventtap.event
  event.newKeyEvent({"ctrl"}, "ctrl", true):post()
  event.newKeyEvent({"ctrl", "alt"}, "alt", true):post()
  event.newKeyEvent({"ctrl", "alt"}, "space", true):post()
  event.newKeyEvent({"ctrl", "alt"}, "space", false):post()
  event.newKeyEvent({"ctrl"}, "alt", false):post()
  event.newKeyEvent({}, "ctrl", false):post()
end

local function sourceChanged()
  local current = hs.keycodes.currentSourceID()
  if not target then rememberCurrent(); return end
  if current == target then finish(); return end
  if waiting and current ~= stepSource then
    waiting = false
    timer:stop()
    timer = hs.timer.doAfter(0, advance)
  end
end

local function selectSource(source)
  local available, count = {}, 0
  for _, list in ipairs({hs.keycodes.layouts(true), hs.keycodes.methods(true)}) do
    for _, id in ipairs(list) do
      if not available[id] then available[id] = true; count = count + 1 end
    end
  end
  if not available[source] then
    hs.alert.show("Enable Korean 2-Set and Japanese Romaji in Keyboard > Text Input")
    return false
  end
  local shortcut = hs.hotkey.systemAssigned({"ctrl", "alt"}, "space")
  if not shortcut or not shortcut.enabled then
    hs.alert.show("Enable Control-Option-Space for Select the next source in Input menu")
    return false
  end
  target, steps, limit = source, 0, count
  -- A second key press changes the destination, without racing another switch.
  -- Return from the Carbon hotkey handler before posting another shortcut.
  if not timer then timer = hs.timer.doAfter(0, advance) end
  return true
end

local function toggleEnglish()
  local current = target or rememberCurrent()
  return selectSource(current == english and lastAsian or english)
end

local function toggleAsian()
  local current = target or rememberCurrent()
  local asian = isAsian(current) and current or lastAsian
  return selectSource(asian == korean and japanese or korean)
end

rememberCurrent()
hs.keycodes.inputSourceChanged(sourceChanged)

-- Karabiner maps Caps Lock to F16 and a standalone Fn/Globe tap to F17.
-- F16 retains held modifiers, including Shift overlapping the end of a word.
local capsModifiers = {{}}
for _, modifier in ipairs({"shift", "ctrl", "alt", "cmd"}) do
  for i = 1, #capsModifiers do
    local mods = {table.unpack(capsModifiers[i])}
    mods[#mods + 1] = modifier
    capsModifiers[#capsModifiers + 1] = mods
  end
end
for _, mods in ipairs(capsModifiers) do
  bindings[#bindings + 1] = hs.hotkey.bind(mods, "f16", toggleEnglish)
end
bindings[#bindings + 1] = hs.hotkey.bind({}, "f17", toggleAsian)

local function stop()
  cancel()
  hs.keycodes.inputSourceChanged(nil)
  for _, binding in ipairs(bindings) do binding:delete() end
end

return { toggleEnglish = toggleEnglish, toggleAsian = toggleAsian, stop = stop }
