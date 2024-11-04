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

hs.hotkey.bind({'ctrl'}, '[', function() hs.eventtap.keyStrokes("[") end)
hs.hotkey.bind({'ctrl'}, ']', function() hs.eventtap.keyStrokes("]") end)
hs.hotkey.bind({'ctrl'}, "'", function() hs.eventtap.keyStrokes("'") end)
hs.hotkey.bind({'ctrl', 'shift'}, "'", function() hs.eventtap.keyStrokes('"') end)
hs.hotkey.bind({'ctrl'}, "/", function() hs.eventtap.keyStrokes("/") end)
hs.hotkey.bind({'ctrl', 'shift'}, "/", function() hs.eventtap.keyStrokes("?") end)
hs.hotkey.bind({'ctrl', 'shift'}, "3", function() hs.eventtap.keyStrokes("#") end)
