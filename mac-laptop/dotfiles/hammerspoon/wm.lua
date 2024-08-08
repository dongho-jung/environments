local function maximizeWindow(win)
    if win:isStandard() and win:frame().w > 0 and win:frame().h > 0 then
        win:maximize()
    end
end

local windowFilter = hs.window.filter.new(false):setFilters({
    ['PyCharm'] = true,
    ['Google Chrome'] = true,
    ['DataGrip'] = true,
    ['Slack'] = true
})
windowFilter:subscribe(hs.window.filter.windowMoved, maximizeWindow)

local arrangeDesktop = hs.loadSpoon('ArrangeDesktop')
arrangeDesktop.logger.setLogLevel('debug')
arrangeDesktop:addMenuItems()

hs.hotkey.bind({'command'}, 'f3', function()
    arrangeDesktop:createArrangement()
end)

hs.hotkey.bind({}, 'f3', function()
    arrangeDesktop:arrange('three-monitors')
    hs.alert.show('Arranged desktop for three-monitors')
end)
