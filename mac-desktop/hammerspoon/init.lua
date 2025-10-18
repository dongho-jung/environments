require('modules.input-switch')
require('modules.tiling')
require('modules.pad')
require('modules.dropdown')

hs.loadSpoon("ReloadConfiguration")
spoon.ReloadConfiguration:start()

hs.alert.show('Hammerspoon Started...')
