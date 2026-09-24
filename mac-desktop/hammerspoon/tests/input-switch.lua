local path = hs.configdir .. "/input-switch.lua"
local en = 'com.apple.keylayout.ABC'
local kr = 'com.apple.inputmethod.Korean.2SetKorean'
local jp = 'com.apple.inputmethod.Kotoeri.RomajiTyping.Japanese'
local function run()
  local current, saved, fail, alerts, changed = en, nil, nil, 0, nil
  local bindings = {}
  local mock = {
    settings = {get = function() return saved end, set = function(_, v) saved = v end},
    alert = {show = function() alerts = alerts + 1 end},
    hotkey = {bind = function(_, key, callback) bindings[key] = callback end},
    keycodes = {
      currentSourceID = function(source)
        if not source then return current end
        if source == fail then return false end
        current = source
        return true
      end,
      inputSourceChanged = function(callback) changed = callback end,
    },
  }
  local function reload() return assert(loadfile(path, 't', {hs = mock}))() end
  local m = reload()
  assert(bindings.f16 and bindings.f17)
  assert(m.toggleEnglish() and current == kr, 'fresh English -> Korean')
  assert(m.toggleAsian() and current == jp, 'Korean -> Japanese')
  assert(m.toggleEnglish() and current == en, 'Japanese -> English')
  assert(m.toggleEnglish() and current == jp, 'English -> remembered Japanese')
  assert(m.toggleAsian() and current == kr, 'Japanese -> Korean')
  assert(m.toggleEnglish() and current == en)
  m = reload()
  assert(m.toggleEnglish() and current == kr, 'remember across reload')
  current = jp; changed()
  current = en; changed()
  assert(m.toggleEnglish() and current == jp, 'remember external switch')
  assert(m.toggleEnglish() and current == en)
  assert(m.toggleAsian() and current == kr, 'Fn from English -> other Asian')
  fail = jp
  assert(not m.toggleAsian() and current == kr and saved == kr and alerts == 1, 'failed selection preserves state')
end
run()
print("PASS: input switching, remembered state, reload, and selection failures")
