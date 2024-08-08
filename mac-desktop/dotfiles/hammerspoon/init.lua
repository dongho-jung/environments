require('modules.terminal')
require('modules.input-switch')
require('modules.tiling')
require('modules.misc-hotkeys')

hs.loadSpoon("ReloadConfiguration")
spoon.ReloadConfiguration:start()

hs.alert.show('Hammerspoon Started...')
