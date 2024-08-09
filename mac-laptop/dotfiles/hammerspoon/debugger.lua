hs.hotkey.bind({"cmd", "shift"}, "f4", function()
    local win = hs.window.focusedWindow()
    if win then
        local appName = win:application():name()
        local message = "Focused window's application: " .. appName .. " (" .. win:id() .. ")"
        print(message)
        hs.alert.show(message)
    else
        local message = "No focused window"
        print(message)
        hs.alert.show(message)
    end
end)

hs.hotkey.bind({"cmd", "shift"}, "f3", function()
    local space = hs.spaces.focusedSpace()
    if space then
        local message = "Focused space: " .. space
        print(message)
        hs.alert.show(message)
    else
        local message = "No focused space"
        print(message)
        hs.alert.show(message)
    end
end)
