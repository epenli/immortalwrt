local json=require 'luci.jsonc'
local updater=dofile(arg[1])
local checksum=string.rep('a',64)
local function entry(name) return {name=name,sha256=checksum,size=10,url='https://github.com/epenli/immortalwrt/releases/download/passwall-build-1-1/jdcloud-'..name..'.apk'} end
local doc={schema=1,device='jdcloud',passwall={version='26.9.27-r1',packages={entry('luci-app-passwall'),entry('luci-i18n-passwall-zh-cn')}}}
local files={['/tmp/sysinfo/board_name']='jdcloud,re-ss-01'}
local calls={}
local api={jsonc=json,CACHE_PATH='/tmp/test-cache',trim=function(s)return s:match('^%s*(.-)%s*$')end,
 clone=function(x)return x end,util={shellquote=function(s)return "'"..s.."'"end},
 compare_versions=function(a,b,c)return a~=c end,
 fs={readfile=function(p)return files[p]end,mkdir=function(p)files[p]=true;return true end,
 remove=function(p)files[p]=nil end,rmdir=function(p)files[p]=nil end,stat=function()return 10 end},
 sys={exec=function(cmd)if cmd:match('^apk query')then return '[{"version":"26.9.16-r1"}]'end;return checksum..' file'end,
 call=function(cmd)calls[#calls+1]=cmd;assert(cmd:find('%-%-simulate'),'unexpected install or migration');assert(cmd:find(' </dev/null ',1,true),'APK stdin must be open');return 1 end},
 curl_auto=function(url,path,args) assert(not table.concat(args,' '):find('%-k'));return 0,json.stringify(doc)end}
updater.install(api)
assert(api.to_check_self().has_update==true)
doc.device='ufi';assert(api.to_check_self().code==1);doc.device='jdcloud'
doc.passwall.packages[1].url='http://bad.invalid/file.apk';assert(api.to_check_self().code==1)
doc.passwall.packages[1]=entry('luci-app-passwall')
doc.passwall.packages[2]=entry('luci-app-passwall');assert(api.to_check_self().code==1)
doc.passwall.packages[2]=entry('luci-i18n-passwall-zh-cn')
local r=api.install_self();assert(r.code==1 and r.error:find('依赖检查'))
assert(#calls==1 and not files['/tmp/passwall-apk-update.lock'])
print('Self updater: valid version, wrong device, URL rejection, duplicate APK and dependency refusal passed')
