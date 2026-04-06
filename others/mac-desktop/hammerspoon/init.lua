require('modules.input-switch')
require('modules.remap')
require('modules.pad')

hs.loadSpoon("ReloadConfiguration")
spoon.ReloadConfiguration:start()

hs.alert.show('Hammerspoon Started...')
