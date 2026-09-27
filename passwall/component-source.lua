-- Adapt the existing PassWall component buttons to this repository's releases.
local M = {}
function M.install(api)
    local fs, sys, json = api.fs, api.sys, api.jsonc
    local com = require 'luci.passwall.com'
    local boards = { ['jdcloud,re-ss-01'] = 'jdcloud', ['thwc,ufi001c'] = 'ufi' }
    local device = boards[api.trim(fs.readfile('/tmp/sysinfo/board_name') or '')]
    if not device then return end
    local names = { xray=true, ['sing-box']=true, hysteria=true, geoview=true, ['chinadns-ng']=true }
    local base = 'https://github.com/epenli/immortalwrt/releases/'
    local channel = base .. 'download/passwall-components-' .. device .. '/components.json'
    local args = { '-sfL', '--proto =https --proto-redir =https', '--connect-timeout 10', '--max-time 180', '--retry 2' }
    local old_check, old_download, old_move = api.to_check, api.to_download, api.to_move
    local function fail(message) return { code=1, error=message } end
    local function record(app) return '/tmp/passwall-component-' .. app .. '.json' end
    local function sha(path)
        return api.trim(sys.exec('sha256sum ' .. api.util.shellquote(path) .. ' 2>/dev/null')):match('^(%x+)')
    end
    local function metadata(app)
        local rc, body = api.curl_auto(channel, nil, api.clone(args))
        if rc ~= 0 then return nil, '本设备尚无已发布的构建，或 GitHub 暂时无法访问' end
        local manifest = json.parse(body or '')
        if type(manifest) ~= 'table' or manifest.schema ~= 1 or manifest.device ~= device then
            return nil, '组件清单的设备或格式不匹配'
        end
        local item = type(manifest.components) == 'table' and manifest.components[app]
        if type(item) ~= 'table' or type(item.version) ~= 'string' or
           not item.version:match('^[%w%.%+%_%-]+$') or
           type(item.sha256) ~= 'string' or #item.sha256 ~= 64 or not item.sha256:match('^%x+$') or
           type(item.size) ~= 'number' or item.size <= 0 or item.size > 200*1024*1024 or
           type(item.url) ~= 'string' or not item.url:match('^https://github%.com/epenli/immortalwrt/releases/download/passwall%-build%-%d+%-%d+/[%w%.%_%-]+$') then
            return nil, '组件清单校验失败'
        end
        return item
    end
    for app in pairs(names) do com[app].zipped = false end
    api.to_check = function(arch, app)
        if not names[app] then return old_check(arch, app) end
        local item, err = metadata(app)
        if not item then return fail(err) end
        local current = api.get_app_version(app)
        return { code=0, local_version=current, remote_version=item.version,
            has_update=api.compare_versions((current or ''):gsub('^v',''), '<', item.version:gsub('^v','')),
            html_url=base .. 'tag/passwall-components-' .. device,
            data={browser_download_url=item.url, size=item.size} }
    end
    api.to_download = function(app, url, size)
        if not names[app] then return old_download(app, url, size) end
        local item, err = metadata(app)
        if not item then return fail(err) end
        if url ~= item.url then return fail('发布版本已变化，请刷新页面重新检查更新') end
        local old = json.parse(fs.readfile(record(app)) or '')
        if type(old) == 'table' and type(old.file) == 'string' and old.file:match('^/tmp/pwcomponent%.[%w]+$') then fs.remove(old.file) end
        fs.remove(record(app))
        local path = api.trim(sys.exec('mktemp /tmp/pwcomponent.XXXXXXXX'))
        if not path:match('^/tmp/pwcomponent%.[%w]+$') then return fail('无法创建下载临时文件') end
        local rc = api.curl_auto(item.url, path, api.clone(args))
        if rc ~= 0 or fs.stat(path, 'size') ~= item.size or sha(path) ~= item.sha256 then
            fs.remove(path)
            return fail('组件下载失败或 SHA-256 校验不通过，未替换现有程序')
        end
        item.file = path
        fs.writefile(record(app), json.stringify(item))
        fs.chmod(record(app), 384) -- 0600
        return { code=0, file=path, zip=false }
    end
    api.to_move = function(app, file)
        if not names[app] then return old_move(app, file) end
        local item = json.parse(fs.readfile(record(app)) or '')
        if type(item) ~= 'table' or type(file) ~= 'string' or file ~= item.file or
           not file:match('^/tmp/pwcomponent%.[%w]+$') or sha(file) ~= item.sha256 then
            return fail('下载记录或文件校验不通过，请重新检查更新')
        end
        fs.chmod(file, 493) -- 0755
        local candidate = api.get_app_version(app, file)
        if candidate:gsub('^v','') ~= item.version:gsub('^v','') then
            fs.remove(file); fs.remove(record(app))
            return fail('新组件无法运行或版本不匹配，保留现有程序')
        end
        local target = api.get_app_path(app)
        if not target or not target:match('^/[%w%._/%-]+$') then return fail('组件安装路径无效') end
        local backup = target .. '.passwall-previous'
        if fs.access(target) and not fs.copy(target, backup) then return fail('备份旧组件失败，未安装更新') end
        local was_running = sys.call('busybox pgrep -af "passwall/.*' .. app .. '" >/dev/null') == 0
        local result = old_move(app, file)
        if result.code ~= 0 then
            if fs.access(backup) then fs.copy(backup, target); fs.chmod(target, 493) end
            -- The original move may have stopped PassWall before failing.
            if was_running then sys.call('/etc/init.d/passwall restart >/dev/null 2>&1 &') end
        end
        fs.remove(file); fs.remove(record(app))
        return result
    end
end
return M
