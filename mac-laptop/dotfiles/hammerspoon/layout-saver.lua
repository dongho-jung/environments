function _compareTables(t1, t2)
    if type(t1) ~= "table" or type(t2) ~= "table" then
        return false
    end

    for key in pairs(t1) do
        if t2[key] == nil then
            return false
        end
    end

    for key in pairs(t2) do
        if t1[key] == nil then
            return false
        end
    end

    for key, value1 in pairs(t1) do
        local value2 = t2[key]

        if type(value1) == "table" and type(value2) == "table" then
            if not _compareTables(value1, value2) then
                return false
            end
        else
            if value1 ~= value2 then
                return false
            end
        end
    end

    return true
end

local configFile = "~/.layout-saver.json"

function _writeConfiguration(config)
    return hs.json.write(config, configFile, true, true)
end

function _loadConfiguration()
    local config = {}
    local fileExists = hs.fs.displayName('~/.layout-saver.json')

    if fileExists == nil then
        if hs.json.write(config, '~/.layout-saver.json', true, true) == false then
            hs.dialog.blockAlert("Error", "Unable to write out initial layout configuration file.")
            return nil
        end
    else
        config = hs.json.read('~/.layout-saver.json')
        if config == nil then
            return nil
        end
    end

    return config
end

function arrange(layout)
    local allSpaces = hs.spaces.allSpaces()
    for screenUUID, spaces in pairs(allSpaces) do
        for spaceIdx, spaceID in ipairs(spaces) do
            hs.spaces.gotoSpace(spaceID)

            local windowIDs = hs.spaces.windowsForSpace(spaceID)

            local validWindowIDs = hs.fnutils.filter(windowIDs, function(windowID)
                local window = hs.window.get(windowID)
                return window and window:isVisible() and window:id() ~= 0
            end)

            for _, windowID in ipairs(validWindowIDs) do
                local window = hs.window.get(windowID)
                local app = window:application()
                local appBundleID = app:bundleID()

                local attributes = layout[appBundleID]
                if attributes == nil then
                    print("No layout found for " .. appBundleID)
                    goto continue
                end

                local targetSpaces = allSpaces[attributes['screen']['uuid']]
                if targetSpaces == nil then
                    hs.dialog.blockAlert("Error", attributes['screen']['name'] .. " is not a valid screen now")
                    return
                end
                while #(hs.spaces.allSpaces()[attributes['screen']['uuid']]) < attributes['spaceIdx'] do
                    hs.spaces.addSpaceToScreen(attributes['screen']['uuid'])
                end

                hs.spaces.moveWindowToSpace(windowID, targetSpaces[attributes['spaceIdx']])
                window:setFrame(attributes['frame'], 0)

                ::continue::
            end
        end
    end
end

function _buildLayout()
    local layout = {}

    local allSpaces = hs.spaces.allSpaces()
    for screenUUID, spaces in pairs(allSpaces) do
        for spaceIdx, spaceID in ipairs(spaces) do
            hs.spaces.gotoSpace(spaceID)

            local windowIDs = hs.spaces.windowsForSpace(spaceID)

            local validWindowIDs = hs.fnutils.filter(windowIDs, function(windowID)
                local window = hs.window.get(windowID)
                return window and window:isVisible() and window:id() ~= 0
            end)

            for _, windowID in ipairs(validWindowIDs) do
                local window = hs.window.get(windowID)
                local app = window:application()
                local appBundleID = app:bundleID()

                attributes = {
                    ['screen'] = {
                        ['name'] = window:screen():name(),
                        ['uuid'] = screenUUID
                    },
                    ['frame'] = {
                        ['x'] = window:frame().x,
                        ['y'] = window:frame().y,
                        ['w'] = window:frame().w,
                        ['h'] = window:frame().h
                    },
                    ['spaceIdx'] = spaceIdx
                }

                if layout[appBundleID] == nil then
                    layout[appBundleID] = attributes
                else
                    if not _compareTables(layout[appBundleID], attributes) then
                        local errorMessage = app:name() .. " has multiple windows with different attributes"
                        hs.dialog.blockAlert("Error", errorMessage)
                        return
                    end
                end
            end
        end
    end

    return layout
end

function createLayout()
    local continue = hs.dialog.blockAlert("Welcome to \"Layout Saver\"!", "If your application windows are sized and arranged as you like, click \"OK\" to continue. Otherwise, click \"Cancel\"", "OK", "Cancel")
    if continue == "Cancel" then
        return
    end

    local buttonPressed, layoutName = hs.dialog.textPrompt("Name this Layout:", "", "e.g., Office", "OK", "Cancel")
    if buttonPressed == "Cancel" then
        return
    end

    hs.dialog.blockAlert("We will now record each of your workspaces.", "Please don't touch anything until the recording is finished.")

    local config = {}

    config[layoutName] = _buildLayout()

    written = _writeConfiguration(config)
    if written == false then
        hs.dialog.blockAlert("We could not create your layout configuration file.", "", "OK")
        return
    end

    hs.dialog.blockAlert("Your layout has been saved!", "Good luck.", "OK")

    print(hs.inspect.inspect(config))
end

hs.hotkey.bind({ 'command' }, 'f3', function()
    hs.alert.show('Layout Saver started...')
    createLayout()
    hs.alert.show('Layout Saver finished...')
end)

hs.hotkey.bind({}, 'f3', function()
    hs.alert.show('Layout Saver started...')
    local config = _loadConfiguration()
    arrange(config['three-monitors'])
    hs.alert.show('Layout Saver finished...')
end)
