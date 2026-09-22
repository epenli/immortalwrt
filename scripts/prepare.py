#!/usr/bin/env python3
"""Apply small, audited changes to the pinned source; fail on unexpected input."""
import pathlib
import shutil
import sys
import subprocess
from ufi_features import install as install_ufi_features

recipe = pathlib.Path(__file__).resolve().parents[1]
source = pathlib.Path(sys.argv[1]).resolve()
subprocess.run([sys.executable, str(recipe / 'scripts/test-ufi-features.py')], check=True)
# These four feed hashes describe a different archive packing result. The pinned
# build system checked out the exact commits below and reported these SHA-256s.
# Keep fixed commits and strict hash verification; never use MIRROR_HASH=skip.
archive_hashes = {
    'utils/gc/Makefile': (
        '1e2b4d9480cf75663212a2bb7c550f3aae07ef50',
        '58f8ad3f91e8488acc6f034ba0da1efb13a39cfe94f397047a72be827c076bc3',
        '5daf9d3b11e27695ce92bf6405e94fb798322ad539b0e23bfe54f9c056358654'),
    'utils/rmtfs/Makefile': (
        '586372e575f5cc1a7cbb170219ab6df98f394cae',
        '6086bb554c1f604a7e15d9010e3ccfea01cda88cb1df2978944f2a150136848d',
        'c68d6259bd2067b539a81012ba1206ea704b970fecd19722c11fb8f369473a3e'),
    'libs/libusbgx/Makefile': (
        'dbedf16f80c5b4e1807ea4f80cc89d1f15d36f0a',
        '43ebc3de10dc5de12cc390e16330e2844166fb80b53c1f2a0b77b9a98970a368',
        '83b97e503f72189860309bcda9aa06e0e1d46d02dc6984a29c2d54b28aa5e100'),
    'utils/qrtr/Makefile': (
        '5923eea97377f4a3ed9121b358fd919e3659db7b',
        '783cbf7846675eeeea7f24758c996f0fd144fb1e166ce6686afd7f7d89aaa3c6',
        '4badf13925618bdfa460035027bac2813ce849d0d882ccd5d76805ba7d208bea'),
}
for path, (commit, old_hash, new_hash) in archive_hashes.items():
    makefile = source / 'feeds/openstick' / path
    text = makefile.read_text()
    if f'PKG_SOURCE_VERSION:={commit}' not in text or text.count(f'PKG_MIRROR_HASH:={old_hash}') != 1:
        raise SystemExit(f'Unexpected source or mirror hash in {path}; review before updating')
    makefile.write_text(text.replace(f'PKG_MIRROR_HASH:={old_hash}', f'PKG_MIRROR_HASH:={new_hash}'))
    print(f'Pinned archive SHA-256 corrected: {path}')
tweak = source / 'feeds/openstick/utils/openstick-tweaks/files/openstick_tweak'
original = tweak.read_text()
start = original.index('# set dns\n')
end = original.index('# restart network\n', start)
# Use DHCP/carrier-provided DNS instead of an upstream hard-coded resolver list.
updated = original[:start] + original[end:]
updated = updated.replace('# bind usb0 to br-lan',
    '[ -e /etc/ufi-config-restored ] && exit 0\n\n# bind usb0 to br-lan', 1)
updated = updated.replace('apk del openstick-tweaks', '# Keep package metadata for reproducible inspection.')
tweak.write_text(updated)
# Only the flash page needs a longer client timeout for hashing the uploaded
# compressed image on this A53. Full raw hashing runs later outside RPC.
flash = source / 'feeds/luci/modules/luci-mod-system/htdocs/luci-static/resources/view/system/flash.js'
text = flash.read_text()
needle = "const callSystemValidateFirmwareImage = rpc.declare({"
if text.count(needle) != 1:
    raise SystemExit('Unexpected LuCI flash view; review timeout adaptation')
flash.write_text(text.replace(needle,
    "L.env.rpctimeout = Math.max(L.env.rpctimeout || 20, 180);\n\n" + needle))
# Backport only the verified Xray version/hash; keep the pinned feed xray_recipe.
xray = source / 'feeds/packages/net/xray-core/Makefile'
xray_recipe = xray.read_text()
for old, new in (
    ('PKG_VERSION:=26.3.27', 'PKG_VERSION:=26.9.9'),
    ('PKG_HASH:=992a4997e6bb846d11469435d687f99ef812fcde1e0a009bb8e95189ea20331d',
     'PKG_HASH:=efb871a981690688191433a76beef7afdab6750d53cc1775cf8e9e995730ef22'),
):
    if xray_recipe.count(old) != 1:
        raise SystemExit('Pinned Xray xray_recipe changed; review the backport')
    xray_recipe = xray_recipe.replace(old, new)
xray.write_text(xray_recipe)
shutil.copyfile(recipe / 'config.seed', source / '.config')
shutil.copytree(recipe / 'files', source / 'files', dirs_exist_ok=True)
(source / 'files/etc/uci-defaults/zz-ufi-local').chmod(0o755)
install_ufi_features(source)
print('Prepared UFI003 profile with UFI001C DTS; upstream hardware services retained.')
