#!/usr/bin/env python3
"""Apply small, audited changes to the pinned source; fail on unexpected input."""
import pathlib
import shutil
import sys

recipe = pathlib.Path(__file__).resolve().parents[1]
source = pathlib.Path(sys.argv[1]).resolve()
tweak = source / 'feeds/openstick/utils/openstick-tweaks/files/openstick_tweak'
original = tweak.read_text()
start = original.index('# set dns\n')
end = original.index('# restart network\n', start)
# Use DHCP/carrier-provided DNS instead of an upstream hard-coded resolver list.
updated = original[:start] + original[end:]
updated = updated.replace('apk del openstick-tweaks', '# Keep package metadata for reproducible inspection.')
tweak.write_text(updated)
shutil.copyfile(recipe / 'config.seed', source / '.config')
shutil.copytree(recipe / 'files', source / 'files', dirs_exist_ok=True)
(source / 'files/etc/uci-defaults/zz-ufi-local').chmod(0o755)
print('Prepared UFI003 profile with UFI001C DTS; upstream hardware services retained.')
