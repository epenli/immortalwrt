#!/usr/bin/env python3
"""Integrate the pinned ModemManager SMS UI with tested UFI defaults."""
from pathlib import Path
import shutil
import sys

recipe = Path(__file__).resolve().parents[1]
package = Path(sys.argv[1]) / 'feeds/smsmanager/luci-app-sms-manager'
assert 'PKG_VERSION:=1.0.9' in (package / 'Makefile').read_text(encoding='utf-8')
config = package / 'root/etc/config/sms_manager'
text = config.read_text(encoding='utf-8')
for old, new in [("option readport ''", "option readport 'any'"),
                 ("option sendport ''", "option sendport 'any'"),
                 ("option pnumber '+48'", "option pnumber '+86'")]:
    assert text.count(old) == 1, old
    text = text.replace(old, new)
config.write_text(text, encoding='utf-8')
views = package / 'htdocs/luci-static/resources/view/modem'
config_view = views / 'sms_manager_config.js'
text = config_view.read_text(encoding='utf-8')
needle = 'var modems = [];'
assert text.count(needle) == 1
text = text.replace(needle,
    "var modems = [{path: 'any', index: -1, displayName: '自动选择 / Automatic'}];")
config_view.write_text(text, encoding='utf-8')
shutil.copyfile(recipe / 'build-support/sms/sms_manager_readsms.js',
                views / 'sms_manager_readsms.js')
print('Prepared pinned SMS Manager, Chinese package selection and storage-copy deduplication.')
