"""Apply a small component-updater adapter to a LuCI package tree or live root."""
from pathlib import Path
import shutil
import sys
import hashlib
import json
import tarfile
import tempfile
import urllib.request


def install(root, live=False):
    recipe = Path(__file__).resolve().parent
    if live:
        module = root / 'usr/lib/lua/luci/passwall'
        page = root / 'usr/lib/lua/luci/model/cbi/passwall/client/app_update.lua'
    else:
        package = root / 'feeds/luci/applications/luci-app-passwall'
        pin = json.loads((recipe / 'source.json').read_text())
        archive = root / 'dl' / ('passwall-' + pin['commit'] + '.tar.gz')
        archive.parent.mkdir(exist_ok=True)
        if not archive.exists():
            url = f"https://codeload.github.com/{pin['repository']}/tar.gz/{pin['commit']}"
            with urllib.request.urlopen(url, timeout=90) as response:
                archive.write_bytes(response.read())
        if hashlib.sha256(archive.read_bytes()).hexdigest() != pin['sha256']:
            raise SystemExit('PassWall source archive checksum mismatch')
        with tempfile.TemporaryDirectory() as tmp:
            with tarfile.open(archive) as source:
                source.extractall(tmp, filter='data')
            candidates = list(Path(tmp).glob('*/luci-app-passwall'))
            if len(candidates) != 1 or f"PKG_VERSION:={pin['version']}" not in (candidates[0] / 'Makefile').read_text():
                raise SystemExit('Unexpected PassWall source version')
            shutil.rmtree(package)
            shutil.copytree(candidates[0], package)
        module = package / 'luasrc/passwall'
        page = package / 'luasrc/model/cbi/passwall/client/app_update.lua'
    api = module / 'api.lua'
    text = api.read_text()
    hook = '\n-- Local verified component release channel.\nrequire("luci.passwall.component-source").install(_M)\n'
    if hook not in text:
        if 'function to_check(arch, app_name)' not in text or 'function to_move(app_name,file)' not in text:
            raise SystemExit('PassWall update API changed; adapter needs review')
        api.write_text(text.rstrip() + '\n' + hook)
    shutil.copyfile(recipe / 'component-source.lua', module / 'component-source.lua')
    self_hook = '\nrequire("luci.passwall.self-source").install(_M)\n'
    if self_hook not in api.read_text():
        api.write_text(api.read_text() + self_hook)
    shutil.copyfile(recipe / 'self-source.lua', module / 'self-source.lua')
    controller = module.parent / 'controller/passwall.lua'
    text = controller.read_text()
    entry = '\tentry({"admin", "services", appname, "update_passwall"}, post("app_install")).leaf = true\n'
    anchor = '\tentry({"admin", "services", appname, "check_passwall"}, call("app_check")).leaf = true'
    if entry not in text:
        if text.count(anchor) != 1: raise SystemExit('Unexpected PassWall controller')
        text = text.replace(anchor, anchor + '\n' + entry)
        text += '\nfunction app_install()\n http_write_json(api.install_self())\nend\n'
        controller.write_text(text)
    template = module.parent / 'view/passwall/app_update/app_version.htm'
    text = template.read_text()
    anchor = '\t\t// Download file'
    patch = (recipe / 'self-update.js').read_text()
    if patch not in text:
        if text.count(anchor) != 1: raise SystemExit('Unexpected PassWall update template')
        template.write_text(text.replace(anchor, patch + '\n' + anchor))
    text = page.read_text()
    label = 's.description = "更新来源：epenli/immortalwrt 已验证构建。本体与核心均可在此检查并更新；本体安装前自动备份配置，代理可能短暂中断。"\n'
    needle = 's:appendTemplate("/app_update/app_version", {com = com})'
    old_label = 's.description = "核心组件来源：epenli/immortalwrt 已验证构建。点击检查更新后安装；PassWall 本体仍通过 APK 更新。"\n'
    text = text.replace(old_label, '')
    if label not in text:
        if text.count(needle) != 1:
            raise SystemExit('PassWall component page changed')
        page.write_text(text.replace(needle, label + needle))


if __name__ == '__main__':
    install(Path(sys.argv[1]), '--live' in sys.argv[2:])
