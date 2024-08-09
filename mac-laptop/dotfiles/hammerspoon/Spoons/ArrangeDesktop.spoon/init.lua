--- === ArrangeDesktop ===
---
--- Easily create, save, and use desktop arrangements.
---
--- Positioning logic adapted from https://github.com/dploeger/hammerspoon-window-manager

local obj = {}
obj.__index = obj

obj.name = "ArrangeDesktop"
obj.version = "2.0.0"
obj.author = "Luis Cruz <sprak3000+github@gmail.com>"
obj.homepage = "https://github.com/Hammerspoon/Spoons"
obj.license = "MIT - https://opensource.org/licenses/MIT"

--- ArrangeDesktop.logger
--- Variable
--- Logger object used within the Spoon. Can be accessed to set the default log level for the messages coming from the Spoon.
obj.logger = hs.logger.new('ArrangeDesktop')

--- ArrangeDesktop.arrangements
--- Variable
--- Contains the configured desktop arrangements
obj.arrangements = {}

--- ArrangeDesktop.configFile
--- Variable
--- Defines where the config file is stored. Defaults to hs.spoons.scriptPath()/config.json
obj.configFile = hs.spoons.scriptPath() .. "config.json"

--- ArrangeDesktop._loadConfiguration() -> table or nil
--- Function
--- Loads the configuration file.
---
--- Parameters:
---  * None
---
--- Returns:
---  * A table containing the configured desktop arrangements, or nil if an error occurred
function obj:_loadConfiguration()
    local config = {}
    local fileExists = hs.fs.displayName(obj.configFile)

    if fileExists == nil then
        if hs.json.write(config, obj.configFile, true, true) == false then
            obj.logger.e("Unable to write out initial Arrange Desktop configuration file.")
            return nil
        end
    else
        config = hs.json.read(obj.configFile)
        if config == nil then
            return nil
        end
    end

    return config
end

--- ArrangeDesktop._writeConfiguration(config) -> bool
--- Function
--- Writes the configuration to a file.
---
--- Parameters:
---  * config - A table containing the configuration to write
---
--- Returns:
---  * A boolean indicating if the write was successful
function obj:_writeConfiguration(config)
    return hs.json.write(config, obj.configFile, true, true)
end

--- ArrangeDesktop._buildArrangement() -> table
--- Function
--- Builds the configuration for the current desktop arrangement.
---
--- Parameters:
---  * None
---
--- Returns:
---  * A table containing the configuration data for the current desktop arrangement
function obj:_buildArrangement()
    local arrangement = {}
    for _, v in pairs(hs.screen.allScreens()) do
        local monitorUUID = v:getUUID()

        arrangement[monitorUUID] = {}
        arrangement[monitorUUID]['Monitor Name'] = v:name()
        arrangement[monitorUUID]['spaces'] = {}

        for _, sv in pairs(hs.spaces.spacesForScreen(monitorUUID)) do
            screenKey = tostring(sv)
            arrangement[monitorUUID]['spaces'][screenKey] = {}
            arrangement[monitorUUID]['spaces'][screenKey]['apps'] = {}

            local windows = hs.window.filter.new(true):setScreens(v:getUUID()):getWindows()
            for _, wv in pairs(windows) do
                if hs.spaces.windowSpaces(wv)[1] ~= sv then
                    goto continue
                end

                arrangement[monitorUUID]['spaces'][screenKey]['apps'][wv:application():title()] = {}

                wv:focus()

                for i, t in pairs(wv:frame()) do
                    local attribute = string.gsub(i, '_', '')
                    arrangement[monitorUUID]['spaces'][screenKey]['apps'][wv:application():title()][attribute] = t
                end

                :: continue ::
            end
        end
    end

    print(hs.inspect.inspect(arrangement))

    return arrangement
end

--- ArrangeDesktop._positionApp(app, appTitle, screen, frame)
--- Function
--- Positions all windows for an application based on the given configuration.
---
--- Parameters:
---  * app - A table of the application instance
---  * appTitle - The name of the application, e.g., Slack, Firefox, etc.
---  * spaceID - The ID of the space to place the application window into
---  * frame - A table of the frame details for the application window, e.g., {w=12, h=12, x=12, y=12}
function obj:_positionApp(app, appTitle, screen, spaceID, frame)
    obj.logger.d('Positioning ' .. appTitle)

    app:activate()
    local windows = hs.window.filter.new(appTitle):getWindows()

    for _, v in pairs(windows) do
        obj.logger.d('Positioning window ' .. v:id() .. ' of app ' .. appTitle)

        hs.spaces.moveWindowToSpace(v, tonumber(spaceID))
        v:setFrame(frame, 0)
    end
end

--- ArrangeDesktop:arrange(arrangement)
--- Method
--- Arrange the desktop based on a given configuration
---
--- Parameters:
---  * arrangement - A table of arrangement data
function obj:arrange(arrangement)
    for monitorUUID, monitorDetails in pairs(obj.arrangements[arrangement]) do
        if hs.screen.find(monitorUUID) ~= nil then
            local validSpaces = {}
            for spaceID, _ in pairs(monitorDetails['spaces']) do
                table.insert(validSpaces, tonumber(spaceID))
            end

            print('Valid Spaces ' .. hs.inspect.inspect(validSpaces))

            for _, spaces in pairs(hs.spaces.allSpaces()) do
                for _, space in ipairs(spaces) do
                    print('Checking space ' .. space)
                    if hs.fnutils.contains(validSpaces, space) == false then
                        print('Removing space ' .. space)
                        hs.spaces.removeSpace(space)
                    end
                end
            end

            for spaceID, spaceDetails in pairs(monitorDetails['spaces']) do
                for appName, position in pairs(spaceDetails['apps']) do
                    app = hs.application.get(appName)
                    if app ~= nil then
                        obj:_positionApp(app, appName, monitorUUID, spaceID, position)
                    end
                end
            end
        end
    end
end

--- ArrangeDesktop:addMenuItems(menuItems) -> table
--- Method
--- Add menu items to a table for each configured desktop arrangement.
---
--- Parameters:
---  * menuItems - A table of menu items to append to
---
--- Returns:
---  * A table of menu items
function obj:addMenuItems(menuItems)
    if menuItems == nil then
        menuItems = {}
    end

    table.insert(menuItems, { title = "Create Desktop Arrangement", fn = function()
        obj:createArrangement()
    end })

    local next = next
    local subMenu = {}
    obj.arrangements = obj:_loadConfiguration()
    --obj.arrangements = {}
    if next(obj.arrangements) ~= nil then
        for k, _ in pairs(obj.arrangements) do
            table.insert(subMenu, { title = k, fn = function()
                obj:arrange(k)
            end })
        end

        table.insert(menuItems, { title = "-" })
        table.insert(menuItems, { title = "Desktop Arrangements", menu = subMenu })
    end

    return menuItems
end

--- ArrangeDesktop:createArrangement()
--- Method
--- Creates the desktop arrangement and saves it to the configuration file.
---
--- Parameters:
---  * None
function obj:createArrangement()
    local config = obj:_loadConfiguration()

    local continue = hs.dialog.blockAlert("Welcome to \"Arrange Desktop\"!", "If your application windows are sized and arranged as you like, click \"OK\" to continue. Otherwise, click \"Cancel\"", "OK", "Cancel")
    if continue == "Cancel" then
        return
    end

    local buttonPressed, arrangementName = hs.dialog.textPrompt("Name this Desktop Arrangement:", "", "e.g., Office", "OK", "Cancel")
    if buttonPressed == "Cancel" then
        return
    end

    hs.dialog.blockAlert("We will now record each of your application windows.", "Each window will flash into focus. The first focus on each monitor will prompt you to name the monitor.")

    config[arrangementName] = obj:_buildArrangement(arrangementName)

    written = obj:_writeConfiguration(config)
    if written == false then
        hs.dialog.blockAlert("We could not create your desktop configuration file.", "", "OK")
        return
    end

    hs.dialog.blockAlert("Your desktop arrangement has been saved!", "Make sure to check your configuration for any duplicate application windows.", "OK")
end

return obj
