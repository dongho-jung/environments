require('modules.input-switch')
require('modules.tiling')
require('modules.pad')
require('modules.remap')

hs.loadSpoon("ReloadConfiguration")
spoon.ReloadConfiguration:start()

hs.alert.show('Hammerspoon Started...')
