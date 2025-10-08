local rememberedWinID = nil

local function winFromID(id)
  if not id then return nil end
  return hs.window.get(id)
end

local function sendKeyToRemembered(mods, key)
  local target = winFromID(rememberedWinID)
  if not target or not target:application() then
    hs.alert.show("저장된 창이 없거나 닫힘")
    return
  end

  local current = hs.window.focusedWindow()
  target:focus()
  hs.timer.doAfter(0.03, function()
    hs.eventtap.keyStroke(mods, key, 0)
    if current and current:id() ~= target:id() then
      hs.timer.doAfter(0.03, function()
        current:focus()
      end)
    end
  end)
end

hs.hotkey.bind({}, "f15", function()
  local w = hs.window.focusedWindow()
  if not w then
    hs.alert.show("포커스된 창 없음")
    return
  end
  rememberedWinID = w:id()
  hs.alert.show("창 저장: " .. (w:title() or "(제목 없음)"))
end)

hs.hotkey.bind({}, "pad5", function()
  sendKeyToRemembered({}, "space")
end)

hs.hotkey.bind({}, "pad4", function()
  sendKeyToRemembered({}, "left")
end)

hs.hotkey.bind({}, "pad6", function()
  sendKeyToRemembered({}, "right")
end)

hs.hotkey.bind({}, "pad1", function()
  sendKeyToRemembered({"shift"}, "p")
end)

hs.hotkey.bind({}, "pad3", function()
  sendKeyToRemembered({"shift"}, "n")
end)

hs.hotkey.bind({}, "pad2", function()
  sendKeyToRemembered({"shift"}, ",")
end)

hs.hotkey.bind({}, "pad8", function()
  sendKeyToRemembered({"shift"}, ".")
end)
