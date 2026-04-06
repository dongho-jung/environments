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

-- 임시 영어 전환 (F16)
hs.hotkey.bind({}, 'f16', temp_eng)

-- 직접 지정 전환 (넘패드 1~3)
hs.hotkey.bind({}, "pad1", function()
  hs.keycodes.currentSourceID("com.apple.keylayout.ABC")
end)
hs.hotkey.bind({}, "pad2", function()
  hs.keycodes.currentSourceID("com.apple.inputmethod.Korean.2SetKorean")
end)
hs.hotkey.bind({}, "pad3", function()
  hs.keycodes.currentSourceID("com.apple.inputmethod.Kotoeri.RomajiTyping.Japanese")
end)

------------------------------------------------------------
-- F17: 입력 소스 순환 전환
------------------------------------------------------------

local input_sources = {
  "com.apple.inputmethod.Kotoeri.RomajiTyping.Japanese",
  "com.apple.keylayout.ABC",
  "com.apple.inputmethod.Korean.2SetKorean"
}

local current_index = 1

local function getCurrentSourceId()
  return hs.keycodes.currentSourceID()
end

local function switchInputSource()
  local current = getCurrentSourceId()

  -- 현재 인덱스 찾기
  for i, id in ipairs(input_sources) do
    if id == current then
      current_index = i
      break
    end
  end

  -- 다음 인덱스 계산
  local next_index = (current_index % #input_sources) + 1
  local next_source = input_sources[next_index]

  hs.keycodes.currentSourceID(next_source)
  hs.alert.show("Input Source: " .. next_source:match("[^.]+$"))
end

hs.hotkey.bind({}, "f17", switchInputSource)

