local path = hs.configdir .. '/input-switch.lua'
local en = 'com.apple.keylayout.ABC'
local kr = 'com.apple.inputmethod.Korean.2SetKorean'
local jp = 'com.apple.inputmethod.Kotoeri.RomajiTyping.Japanese'

local function chord(mods, key)
  local sorted = {table.unpack(mods)}
  table.sort(sorted)
  return table.concat(sorted, '+') .. ':' .. key
end

local function fixture()
  local f = {
    current = en, activeMethod = en, saved = nil, alerts = 0, requests = 0,
    enabled = true, missingJapanese = false, ignoreSwitch = false,
    now = 0, timers = {}, bindings = {},
  }
  local function after(delay, callback)
    local t = {at = f.now + delay, callback = callback, active = true}
    function t:stop() self.active = false end
    f.timers[#f.timers + 1] = t
    return t
  end
  function f.tick()
    local nextTimer
    for _, t in ipairs(f.timers) do
      if t.active and (not nextTimer or t.at < nextTimer.at) then nextTimer = t end
    end
    if not nextTimer then return false end
    f.now, nextTimer.active = nextTimer.at, false
    nextTimer.callback()
    return true
  end
  function f.settle()
    for _ = 1, 30 do if not f.tick() then return end end
    error('input switching did not settle')
  end
  function f.changed()
    if f.onChange then f.onChange() end
  end
  function f.external(source)
    f.current, f.activeMethod = source, source
    f.changed()
  end
  local mock = {
    settings = {get = function() return f.saved end, set = function(_, value) f.saved = value end},
    alert = {show = function() f.alerts = f.alerts + 1 end},
    timer = {doAfter = after},
    hotkey = {
      bind = function(mods, key, callback)
        local name = chord(mods, key)
        f.bindings[name] = callback
        return {delete = function() f.bindings[name] = nil end}
      end,
      systemAssigned = function(mods, key)
        assert(chord(mods, key) == 'alt+ctrl:space')
        return f.enabled and {enabled = true} or false
      end,
    },
    keycodes = {
      currentSourceID = function(source)
        assert(source == nil, 'direct TIS selection does not verify actual IME activation')
        return f.current
      end,
      layouts = function() return {en} end,
      methods = function() return f.missingJapanese and {kr} or {jp, kr} end,
      inputSourceChanged = function(callback) f.onChange = callback end,
    },
    eventtap = {
      keyStroke = function(mods, key, delay)
        assert(chord(mods, key) == 'alt+ctrl:space' and delay == 0)
        f.requests = f.requests + 1
        if f.ignoreSwitch then return end
        after(0.01, function()
          local nextSource = {[en] = jp, [jp] = kr, [kr] = en}
          f.current = nextSource[f.current]
          f.activeMethod = f.current -- Only native switching activates the app's IME.
          f.changed()
          f.changed() -- macOS may send duplicate source notifications.
        end)
      end,
    },
  }
  function f.reload()
    if f.module then f.module.stop() end
    f.module = assert(loadfile(path, 't', {hs = mock, ipairs = ipairs, table = table}))()
  end
  function f.expect(action, source)
    assert(action(), 'switch request rejected')
    f.settle()
    assert(f.current == source and f.activeMethod == source, 'wrong input method')
  end
  f.reload()
  return f
end

local f = fixture()
f.expect(f.module.toggleEnglish, kr)
assert(f.requests == 2 and f.saved == kr, 'walk past Japanese without remembering it')
f.expect(f.module.toggleAsian, jp)
f.expect(f.module.toggleEnglish, en)
f.expect(f.module.toggleEnglish, jp)
f.expect(f.module.toggleAsian, kr)
f.expect(f.module.toggleEnglish, en)
f.reload()
f.expect(f.module.toggleEnglish, kr)
f.external(jp); f.external(en)
f.expect(f.module.toggleEnglish, jp)
f.expect(f.module.toggleEnglish, en)
f.expect(f.module.toggleAsian, kr)
assert(f.alerts == 0)

for _, mods in ipairs({
  {}, {'shift'}, {'ctrl'}, {'alt'}, {'cmd'},
  {'shift', 'ctrl'}, {'shift', 'alt'}, {'shift', 'cmd'},
  {'ctrl', 'alt'}, {'ctrl', 'cmd'}, {'alt', 'cmd'},
  {'shift', 'ctrl', 'alt'}, {'shift', 'ctrl', 'cmd'},
  {'shift', 'alt', 'cmd'}, {'ctrl', 'alt', 'cmd'},
  {'shift', 'ctrl', 'alt', 'cmd'},
}) do
  local press = assert(f.bindings[chord(mods, 'f16')])
  f.external(kr)
  f.expect(press, en)
  f.expect(press, kr)
end

f = fixture()
assert(f.module.toggleEnglish())
f.tick() -- The intermediate Japanese notification must not become lastAsian.
assert(f.saved == nil)
assert(f.module.toggleEnglish()) -- Reverse the pending request before the next step.
f.settle()
assert(f.current == en and f.activeMethod == en and f.requests == 3 and f.saved == nil)

f = fixture()
assert(f.module.toggleEnglish())
assert(f.module.toggleAsian()) -- Change the pending destination to Japanese.
f.settle()
assert(f.current == jp and f.saved == jp and f.requests == 1)

f = fixture()
f.missingJapanese = true
assert(not f.module.toggleAsian() and f.requests == 0 and f.alerts == 1)
f.enabled = false
assert(not f.module.toggleEnglish() and f.requests == 0 and f.alerts == 2)

f = fixture()
assert(f.module.toggleEnglish())
f.tick()
f.enabled = false
f.settle()
assert(f.requests == 1 and f.alerts == 1, 'do not send unhandled shortcuts')

f = fixture()
f.ignoreSwitch = true
assert(f.module.toggleEnglish())
f.settle()
assert(f.current == en and f.alerts == 1 and f.saved == nil, 'timeout preserves remembered source')
f.ignoreSwitch = false
f.expect(f.module.toggleEnglish, kr)

f = fixture()
local originalChanged = f.changed
f.changed = function()
  if f.current == kr then f.current, f.activeMethod = en, en end
  originalChanged()
end
assert(f.module.toggleEnglish())
f.settle()
assert(f.requests == 3 and f.alerts == 1, 'stop after one unsuccessful cycle')

f = fixture()
assert(f.module.toggleEnglish())
f.module.stop()
f.settle()
assert(f.requests == 1 and f.alerts == 0 and next(f.bindings) == nil and f.onChange == nil,
  'unloading cancels pending follow-up switches and releases hotkeys')

print('PASS: native IME switching, 16 modifier combinations, rapid requests, failures, and unload')
