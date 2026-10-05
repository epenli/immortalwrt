// Execute the real patched template with a browser/XHR stub, without network or installs.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(process.argv[2], 'utf8');
const source = html.match(/<script type="text\/javascript">([\s\S]*?)<\/script>/)[1]
    .replace(/<%=api.appname%>/g, 'passwall')
    .replace(/<%=api.url\("update_"\)%>/g, '/update_')
    .replace(/<%[\s\S]*?%>/g, 'test');
for (const result of [{code: 0}, {code: 1, error: 'failed'}, undefined]) {
    let callback, posts = [], gets = [], timers = 0;
    const button = app => ({value: '', disabled: false, getAttribute: () => app});
    const main = button('passwall'), core = button('xray');
    const context = {
        document: {querySelectorAll: () => [main, core], getElementById: () => ({})},
        window: {setTimeout: () => {}, location: {reload: () => {}}},
        setInterval: () => { timers++; }, clearInterval: () => {},
        XHR: {
            post: (url, data, cb) => { posts.push({url, data}); callback = cb; },
            get: (url, data, cb) => { gets.push({url, data});
                if (data.task === 'progress') cb({}, {code: 0});
                else if (data.task === 'move') cb({}, {code: 0});
                else cb({}, {code: 0, zip: false, file: '/tmp/verified'});
            }
        }
    };
    vm.createContext(context); vm.runInContext(source, context);
    // Local self manifest deliberately lacks upstream's data/i18n download fields.
    context.appInfoList.passwall = {has_update: true, remote_version: '26.10.4-r1'};
    context.doUpdate(main, 'passwall');
    assert.equal(posts.length, 1); assert.equal(posts[0].url, '/update_passwall');
    assert.equal(posts[0].data.token, 'test'); assert.equal(gets.length, 0);
    assert.equal(timers, 0); assert.equal(context.luciUpdating, true);
    assert.equal(core.disabled, true);
    context.doUpdate(core, 'xray'); assert.equal(gets.length, 0);
    callback({}, result);
    assert.equal(context.luciUpdating, false); assert.equal(context.inProgressCount, 0);
    assert.equal(context.componentUpdates, 0); assert.equal(core.disabled, false);
    assert.equal(context.window.onbeforeunload, undefined);
    assert.equal(main.disabled, !!result && !result.code);
    if (!result || result.code) {
        assert.equal(context.appInfoList.passwall, undefined);
        context.appInfoList.passwall = {has_update: true};
        context.doUpdate(main, 'passwall'); assert.equal(posts.length, 2);
        callback({}, {code: 0});
    }
    context.appInfoList.xray = {data: {size: 10, browser_download_url: 'https://example.invalid/core'}};
    context.doUpdate(core, 'xray');
    assert.ok(gets.some(request => request.data.task === 'move'));
    assert.equal(context.componentUpdates, 0); assert.equal(context.inProgressCount, 0);
}
console.log('Template: self POST success/failure/empty response/retry, locks and core download/move passed');
