"""Apply a small component-updater adapter to a LuCI package tree or live root."""
from pathlib import Path
import shutil
import sys


def install(root, live=False):
    recipe = Path(__file__).resolve().parent
    if live:
        module = root / 'usr/lib/lua/luci/passwall'
        page = root / 'usr/lib/lua/luci/model/cbi/passwall/client/app_update.lua'
    else:
        package = root / 'feeds/luci/applications/luci-app-passwall'
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
    text = page.read_text()
    label = 's.description = "核心组件来源：epenli/immortalwrt 已验证构建。点击检查更新后安装；PassWall 本体仍通过 APK 更新。"\n'
    needle = 's:appendTemplate("/app_update/app_version", {com = com})'
    if label not in text:
        if text.count(needle) != 1:
            raise SystemExit('PassWall component page changed')
        page.write_text(text.replace(needle, label + needle))


if __name__ == '__main__':
    install(Path(sys.argv[1]), '--live' in sys.argv[2:])
