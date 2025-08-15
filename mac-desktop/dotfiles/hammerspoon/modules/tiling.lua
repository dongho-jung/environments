local function moveFocus(direction)
    local currentWindow = hs.window.focusedWindow()
    if not currentWindow then return end
    
    local currentFrame = currentWindow:frame()
    local currentScreen = currentWindow:screen()
    
    local sameScreenWindows = {}
    for _, window in ipairs(hs.window.visibleWindows()) do
        if window ~= currentWindow and window:screen() and window:screen():id() == currentScreen:id() then
            local windowFrame = window:frame()
            local screenFrame = currentScreen:frame()
            if windowFrame.x >= screenFrame.x and windowFrame.x < (screenFrame.x + screenFrame.w) and
               windowFrame.y >= screenFrame.y and windowFrame.y < (screenFrame.y + screenFrame.h) then
                table.insert(sameScreenWindows, window)
            end
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
            isValidDirection = (windowFrame.y + windowFrame.h) <= currentFrame.y
            if isValidDirection then
                local yDistance = currentFrame.y - (windowFrame.y + windowFrame.h)
                local xOverlap = math.max(0, math.min(currentFrame.x + currentFrame.w, windowFrame.x + windowFrame.w) - 
                                            math.max(currentFrame.x, windowFrame.x))
                distance = yDistance + (xOverlap == 0 and math.abs(currentFrame.x - windowFrame.x) or 0)
            end
        elseif direction == "down" then
            isValidDirection = windowFrame.y >= (currentFrame.y + currentFrame.h)
            if isValidDirection then
                local yDistance = windowFrame.y - (currentFrame.y + currentFrame.h)
                local xOverlap = math.max(0, math.min(currentFrame.x + currentFrame.w, windowFrame.x + windowFrame.w) - 
                                            math.max(currentFrame.x, windowFrame.x))
                distance = yDistance + (xOverlap == 0 and math.abs(currentFrame.x - windowFrame.x) or 0)
            end
        elseif direction == "left" then
            isValidDirection = (windowFrame.x + windowFrame.w) <= currentFrame.x
            if isValidDirection then
                local xDistance = currentFrame.x - (windowFrame.x + windowFrame.w)
                local yOverlap = math.max(0, math.min(currentFrame.y + currentFrame.h, windowFrame.y + windowFrame.h) - 
                                            math.max(currentFrame.y, windowFrame.y))
                distance = xDistance + (yOverlap == 0 and math.abs(currentFrame.y - windowFrame.y) or 0)
            end
        elseif direction == "right" then
            isValidDirection = windowFrame.x >= (currentFrame.x + currentFrame.w)
            if isValidDirection then
                local xDistance = windowFrame.x - (currentFrame.x + currentFrame.w)
                local yOverlap = math.max(0, math.min(currentFrame.y + currentFrame.h, windowFrame.y + windowFrame.h) - 
                                            math.max(currentFrame.y, windowFrame.y))
                distance = xDistance + (yOverlap == 0 and math.abs(currentFrame.y - windowFrame.y) or 0)
            end
        end
        
        if isValidDirection and distance < minDistance then
            minDistance = distance
            targetWindow = window
        end
    end
    
    if targetWindow then
        targetWindow:application():activate()
        targetWindow:becomeMain()
        targetWindow:raise()
    else
        hs.alert.show("No target found (" .. direction .. ")")
    end
end

hs.hotkey.bind({"cmd"}, "up", function() moveFocus("up") end)
hs.hotkey.bind({"cmd"}, "down", function() moveFocus("down") end)
hs.hotkey.bind({"cmd"}, "left", function() moveFocus("left") end)
hs.hotkey.bind({"cmd"}, "right", function() moveFocus("right") end)
