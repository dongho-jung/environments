local bttUUID = "06372360-82CB-4C57-AF70-2929CA61A1C9"

local function handlePadPlus()
  local win = hs.window.frontmostWindow()
  local title = win and win:title() or ""

  if title:find("어사전", 1, true) then
    hs.eventtap.keyStroke({}, "/")
  else
    hs.urlevent.openURL(
      "btt://execute_assigned_actions_for_trigger/?uuid=" .. bttUUID
    )
  end
end

hs.hotkey.bind({}, "pad+", handlePadPlus)
