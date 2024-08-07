local input_sources = {
  "com.apple.keylayout.ABC",
  "com.apple.inputmethod.Korean.2SetKorean",
  "com.apple.inputmethod.Kotoeri.KanaTyping.Japanese"
}
local current_index = 1
hs.hotkey.bind({}, 'f17', function()
  current_index = current_index % #input_sources + 1
  hs.keycodes.currentSourceID(input_sources[current_index])
end)

local prev_input_source = nil
local temp_hotkey = nil
function temp_eng()
  if hs.keycodes.currentSourceID() == "com.apple.keylayout.ABC" then
    if prev_input_source ~= nil then
      hs.keycodes.currentSourceID(prev_input_source)
      temp_hotkey:delete()
    end
    return
  end
  prev_input_source = hs.keycodes.currentSourceID()
  hs.keycodes.currentSourceID("com.apple.keylayout.ABC")
  temp_hotkey = hs.hotkey.bind({}, 'return', temp_eng)
end

hs.hotkey.bind({}, 'f19', temp_eng)
