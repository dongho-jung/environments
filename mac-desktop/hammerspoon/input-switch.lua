local english = "com.apple.keylayout.ABC"
local korean = "com.apple.inputmethod.Korean.2SetKorean"
local japanese = "com.apple.inputmethod.Kotoeri.RomajiTyping.Japanese"
local setting = "inputSwitch.lastAsianSource"

local function isAsian(source)
  return source == korean or source == japanese
end

local lastAsian = hs.settings.get(setting)
if not isAsian(lastAsian) then lastAsian = korean end

local function rememberCurrent()
  local current = hs.keycodes.currentSourceID()
  if isAsian(current) then
    lastAsian = current
    hs.settings.set(setting, current)
  end
  return current
end

local function selectSource(source)
  if not hs.keycodes.currentSourceID(source) then
    hs.alert.show("Enable Korean 2-Set and Japanese Romaji in Keyboard > Text Input")
    return false
  end
  if isAsian(source) then
    lastAsian = source
    hs.settings.set(setting, source)
  end
  return true
end

local function toggleEnglish()
  local current = rememberCurrent()
  return selectSource(current == english and lastAsian or english)
end

local function toggleAsian()
  rememberCurrent()
  return selectSource(lastAsian == korean and japanese or korean)
end

rememberCurrent()
hs.keycodes.inputSourceChanged(rememberCurrent)

-- Karabiner maps Caps Lock to F16 and a standalone Fn/Globe tap to F17.
hs.hotkey.bind({}, "f16", toggleEnglish)
hs.hotkey.bind({}, "f17", toggleAsian)

return { toggleEnglish = toggleEnglish, toggleAsian = toggleAsian }
