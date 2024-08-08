hs.hotkey.bind({"cmd", "shift"}, "F4", function()
    local win = hs.window.focusedWindow()
    if win then
        local appName = win:application():name()
        local message = "Focused window's application: " .. appName
        print(message)
        hs.alert.show(message)
    else
        local message = "No focused window"
        print(message)
        hs.alert.show(message)
    end
end)
