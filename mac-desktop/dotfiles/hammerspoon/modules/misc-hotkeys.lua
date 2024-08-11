hs.hotkey.bind({}, 'f6',
    function()
        hs.timer.doAfter(1, function()
            hs.caffeinate.systemSleep()
        end)
    end
)
