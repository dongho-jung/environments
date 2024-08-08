local function moveFocus(direction)
    local win = hs.window.focusedWindow()
    if not win then return end

    local targetWin
    if direction == "up" then
        targetWin = win:windowsToNorth(nil, true, true)
    elseif direction == "down" then
        targetWin = win:windowsToSouth(nil, true, true)
    elseif direction == "left" then
        targetWin = win:windowsToWest(nil, true, true)
    elseif direction == "right" then
        targetWin = win:windowsToEast(nil, true, true)
    end

    if targetWin and #targetWin > 0 then
        targetWin[1]:focus()
    end
end

hs.hotkey.bind({"alt"}, "up", function() moveFocus("up") end)
hs.hotkey.bind({"alt"}, "down", function() moveFocus("down") end)
hs.hotkey.bind({"alt"}, "left", function() moveFocus("left") end)
hs.hotkey.bind({"alt"}, "right", function() moveFocus("right") end)
