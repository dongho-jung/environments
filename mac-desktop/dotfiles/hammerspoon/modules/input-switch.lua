local prev_input_source = nil
local temp_hotkey = nil

function temp_eng()
  if hs.keycodes.currentSourceID() == "com.apple.keylayout.ABC" then
    if prev_input_source ~= nil then
      hs.keycodes.currentSourceID(prev_input_source)
    end
    return
  end
  prev_input_source = hs.keycodes.currentSourceID()
  hs.keycodes.currentSourceID("com.apple.keylayout.ABC")
end

hs.hotkey.bind({}, 'f19', temp_eng)

hs.hotkey.bind({}, "pad1", function()
  hs.keycodes.currentSourceID("com.apple.keylayout.ABC")
end)
hs.hotkey.bind({}, "pad2", function()
  hs.keycodes.currentSourceID("com.apple.inputmethod.Korean.2SetKorean")
end)
hs.hotkey.bind({}, "pad3", function()
  hs.keycodes.currentSourceID("com.apple.inputmethod.Kotoeri.RomajiTyping.Japanese")
end)
