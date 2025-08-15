local function moveFocus(direction)
    local currentWindow = hs.window.focusedWindow()
    if not currentWindow then return end
    
    local currentFrame = currentWindow:frame()
    local currentScreen = currentWindow:screen()
    local screenFrame = currentScreen:frame()
    
    -- 같은 스크린의 윈도우만 필터링
    local sameScreenWindows = {}
    for _, window in ipairs(hs.window.visibleWindows()) do
        if window ~= currentWindow and window:screen():id() == currentScreen:id() then
            table.insert(sameScreenWindows, window)
        end
    end
    
    if #sameScreenWindows == 0 then return end
    
    local targetWindow = nil
    local minDistance = math.huge
    
    for _, window in ipairs(sameScreenWindows) do
        local windowFrame = window:frame()
        local isValidDirection = false
        local distance = 0
        
        if direction == "up" then
            isValidDirection = windowFrame.y < currentFrame.y
            if isValidDirection then
                distance = currentFrame.y - windowFrame.y
            end
        elseif direction == "down" then
            isValidDirection = windowFrame.y > currentFrame.y
            if isValidDirection then
                distance = windowFrame.y - currentFrame.y
            end
        elseif direction == "left" then
            isValidDirection = windowFrame.x < currentFrame.x
            if isValidDirection then
                distance = currentFrame.x - windowFrame.x
            end
        elseif direction == "right" then
            isValidDirection = windowFrame.x > currentFrame.x
            if isValidDirection then
                distance = windowFrame.x - currentFrame.x
            end
        end
        
        if isValidDirection and distance < minDistance then
            minDistance = distance
            targetWindow = window
        end
    end
    
    if targetWindow then
        targetWindow:focus()
    end
end

hs.hotkey.bind({"cmd"}, "up", function() moveFocus("up") end)
hs.hotkey.bind({"cmd"}, "down", function() moveFocus("down") end)
hs.hotkey.bind({"cmd"}, "left", function() moveFocus("left") end)
hs.hotkey.bind({"cmd"}, "right", function() moveFocus("right") end)
