-- Run with Lua 5.1 and luci.jsonc; all download/filesystem/process operations mocked.
local json = require 'luci.jsonc'
local source = assert(arg[1])
local component = dofile(source)
local base = 'https://github.com/epenli/immortalwrt/releases/download/passwall-build-1-1/'
local doc = {schema=1,device='jdcloud',components={xray={version='26.9.9',
  sha256=string.rep('a',64),size=100,url=base..'jdcloud-xray-linux-arm64'}}}
local files = {['/tmp/sysinfo/board_name']='jdcloud,re-ss-01\n'}
local board = 'jdcloud'
package.loaded['luci.passwall.com'] = {xray={},['sing-box']={},hysteria={},geoview={},['chinadns-ng']={}}
local api = {jsonc=json, fs={readfile=function(p) return files[p] end,
  remove=function(p) files[p]=nil end, stat=function() return 100 end,
  writefile=function(p,v) files[p]=v end, chmod=function() return true end},
  sys={exec=function(command) if command:match('^mktemp') then return '/tmp/pwcomponent.12345678\n' end
    return string.rep('b',64)..'  file' end},
  util={shellquote=function(s) return "'"..s.."'" end},
  trim=function(s) return s:match('^%s*(.-)%s*$') end,
  clone=function(a) return a end,
  get_app_version=function() return '26.9.1' end,
  compare_versions=function() return true end,
  curl_auto=function(url,path,args)
    assert(not table.concat(args,' '):find('%-k'))
    return 0,json.stringify(doc)
  end,
  to_check=function() return 'upstream' end,
  to_download=function() error('unexpected upstream download') end,
  to_move=function() error('must not replace unverified binary') end}
component.install(api)
assert(api.to_check('', 'xray').code==0)
assert(api.to_check('', 'other')=='upstream')
doc.device='ufi';assert(api.to_check('', 'xray').code==1);doc.device='jdcloud'
doc.components.xray.sha256='bad';assert(api.to_check('', 'xray').code==1)
doc.components.xray.sha256=string.rep('a',64)
doc.components.xray.url='https://other.invalid/program';assert(api.to_check('', 'xray').code==1)
doc.components.xray.url=base..'jdcloud-xray-linux-arm64'
assert(api.to_download('xray', 'https://other.invalid/program',100).code==1)
assert(api.to_download('xray', doc.components.xray.url,100).code==1) -- checksum mismatch
assert(api.to_move('xray','/etc/passwd').code==1)
assert(api.to_move('xray',nil).code==1)
print('Component adapter: device, URL, checksum, path and unchanged upstream route checks passed')
