-- Update the PassWall APK pair through the existing authenticated LuCI page.
local M = {}
function M.install(api)
    local fs, sys, json = api.fs, api.sys, api.jsonc
    local devices = {['jdcloud,re-ss-01']='jdcloud', ['thwc,ufi001c']='ufi'}
    local device = devices[api.trim(fs.readfile('/tmp/sysinfo/board_name') or '')]
    if not device then return end
    local channel = 'https://github.com/epenli/immortalwrt/releases/download/passwall-components-' .. device .. '/components.json'
    local args = {'-sfL','--proto =https --proto-redir =https','--connect-timeout 10','--max-time 120','--retry 2'}
    local function fail(e) return {code=1,error=e} end
    local function metadata()
        local rc, body = api.curl_auto(channel, nil, api.clone(args))
        local doc = rc == 0 and json.parse(body or '')
        if type(doc) ~= 'table' or doc.schema ~= 1 or doc.device ~= device or type(doc.passwall) ~= 'table' then
            return nil, '本体 APK 尚未发布或无法获取，请等待构建完成后重试'
        end
        local app = doc.passwall
        if type(app.version) ~= 'string' or not app.version:match('^%d+%.%d+%.%d+%-r%d+$') or
           type(app.packages) ~= 'table' or #app.packages ~= 2 then return nil, 'APK 清单格式无效' end
        local wanted = {['luci-app-passwall']=true, ['luci-i18n-passwall-zh-cn']=true}
        for _, p in ipairs(app.packages) do
            if type(p) ~= 'table' or not wanted[p.name] or type(p.sha256) ~= 'string' or
               #p.sha256 ~= 64 or not p.sha256:match('^%x+$') or type(p.size) ~= 'number' or p.size <= 0 or p.size > 20*1024*1024 or
               type(p.url) ~= 'string' or not p.url:match('^https://github%.com/epenli/immortalwrt/releases/download/passwall%-build%-%d+%-%d+/[%w%.%_%-]+%.apk$') then
                return nil, 'APK 清单校验失败'
            end
            wanted[p.name] = nil
        end
        return app
    end
    local function installed()
        local data = json.parse(sys.exec('apk query --installed --fields name,version --format json luci-app-passwall 2>/dev/null'))
        return type(data)=='table' and data[1] and data[1].version or ''
    end
    api.to_check_self = function()
        local app, err = metadata()
        if not app then return fail(err) end
        local current = installed()
        return {code=0, local_version=current, remote_version=app.version,
            has_update=api.compare_versions(current,'<',app.version),
            html_url='https://github.com/epenli/immortalwrt/releases/tag/passwall-components-' .. device,
            data={}}
    end
    api.install_self = function()
        local lock = '/tmp/passwall-apk-update.lock'
        if not fs.mkdir(lock) then return fail('已有本体更新任务在运行') end
        local function work()
            local app, err = metadata()
            if not app then return fail(err) end
            if not api.compare_versions(installed(), '<', app.version) then
                return fail('已安装同版或更高版本，无需更新')
            end
            local files = {}
            for _, p in ipairs(app.packages) do
                local path = lock .. '/' .. p.name .. '.apk'
                local rc = api.curl_auto(p.url, path, api.clone(args))
                local hash = api.trim(sys.exec('sha256sum ' .. api.util.shellquote(path) .. ' 2>/dev/null')):match('^(%x+)')
                if rc ~= 0 or fs.stat(path,'size') ~= p.size or hash ~= p.sha256 then
                    return fail('APK 下载或 SHA-256 校验失败，未安装')
                end
                files[#files+1] = api.util.shellquote(path)
            end
            local packages = table.concat(files,' ')
            -- LuCI may close stdin. APK can then allocate root_fd=0, which its
            -- script launcher overwrites with a pipe before fchdir(root_fd).
            -- Always open fd 0 before starting APK, including the dry run.
            local command = 'apk --no-network --repositories-file /dev/null add --allow-untrusted '
            local log = lock .. '/result.log'
            if sys.call(command .. '--simulate ' .. packages .. ' </dev/null >' .. log .. ' 2>&1') ~= 0 then
                return fail('依赖检查未通过，未安装：' .. (fs.readfile(log) or ''))
            end
            -- Keep the previous successful backup until a new archive is complete.
            local backup = '/etc/passwall-before-apk-update.tar.gz'
            local paths = {}
            for _, p in ipairs({'etc/config/passwall','etc/config/passwall_server','etc/passwall','usr/share/passwall/rules'}) do
                if fs.access('/' .. p) then paths[#paths+1] = p end
            end
            if #paths == 0 or sys.call('umask 077; tar -czf ' .. backup .. '.new -C / ' .. table.concat(paths,' ')) ~= 0 or
               not fs.rename(backup .. '.new', backup) then return fail('配置备份失败，未安装') end
            -- 26.9.27 moves user rules; preserve old custom rules before APK replacement.
            sys.call('mkdir -p /etc/passwall/rules')
            for _, name in ipairs({'direct_host','direct_ip','proxy_host','proxy_ip','block_host','block_ip','lanlist_ipv4','lanlist_ipv6','domains_excluded'}) do
                local dest = '/etc/passwall/rules/' .. name
                local old = '/usr/share/passwall/rules/' .. name
                if not fs.access(dest) and fs.access(old) and not fs.copy(old,dest) then return fail('规则迁移失败，未安装') end
            end
            local running = sys.call('pgrep -f "[/]tmp/etc/passwall" >/dev/null') == 0
            local rc = sys.call(command .. packages .. ' </dev/null >' .. log .. ' 2>&1')
            local result = fs.readfile(log) or ''
            fs.remove(api.CACHE_PATH .. '/passwall_version')
            if rc ~= 0 or installed() ~= app.version then
                return fail('APK 未完成安装；配置备份保存在 ' .. backup .. '：' .. result)
            end
            fs.remove('/tmp/luci-indexcache')
            if running then sys.call('/etc/init.d/passwall restart >/tmp/passwall-self-update-restart.log 2>&1 &') end
            return {code=0,version=app.version,backup=backup}
        end
        local ok, result = pcall(work)
        -- Only remove this updater's fixed temporary files.
        fs.remove(lock .. '/luci-app-passwall.apk'); fs.remove(lock .. '/luci-i18n-passwall-zh-cn.apk')
        fs.remove(lock .. '/result.log'); fs.rmdir(lock)
        if not ok then return fail('本体更新中断：' .. tostring(result)) end
        return result
    end
end
return M
