require('modules.input-switch')
require('modules.tiling')
require('modules.pad')

hs.loadSpoon("ReloadConfiguration")
spoon.ReloadConfiguration:start()

hs.alert.show('Hammerspoon Started...')
