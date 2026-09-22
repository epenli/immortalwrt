"""Prepare and validate the JDCloud build without changing upstream image recipes."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

RECIPE = Path(__file__).resolve().parent
PROFILE = 'jdcloud_re-ss-01'
BOARD = 'jdcloud,re-ss-01'

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def prepare(build):
    source = (build / 'target/linux/qualcommax/image/ipq60xx.mk').read_text()
    if f'define Device/{PROFILE}' not in source:
        raise SystemExit('Pinned source does not support this device')
    # Backport only the verified Xray version/hash; keep the pinned feed recipe.
    xray = build / 'feeds/packages/net/xray-core/Makefile'
    recipe = xray.read_text()
    for old, new in (
        ('PKG_VERSION:=26.3.27', 'PKG_VERSION:=26.9.9'),
        ('PKG_HASH:=992a4997e6bb846d11469435d687f99ef812fcde1e0a009bb8e95189ea20331d',
         'PKG_HASH:=efb871a981690688191433a76beef7afdab6750d53cc1775cf8e9e995730ef22'),
    ):
        if recipe.count(old) != 1:
            raise SystemExit('Pinned Xray recipe changed; review the backport')
        recipe = recipe.replace(old, new)
    xray.write_text(recipe)
    shutil.copyfile(RECIPE / 'config.seed', build / '.config')
    defaults = build / 'files/etc/uci-defaults/99-jdcloud-clean'
    defaults.parent.mkdir(parents=True, exist_ok=True)
    defaults.write_text("""#!/bin/sh
uci set luci.main.lang='zh_cn'
uci commit luci
# Use the DNS engine verified on this device; do not overwrite restored settings.
if [ "$(uci -q get passwall.@global[0].enabled)" != '1' ]; then
    uci set passwall.@global[0].dns_mode='sing-box'
    uci commit passwall
fi
# Apply the management address only to a fresh configuration.
if [ "$(uci -q get network.lan.ipaddr)" = '192.168.1.1' ]; then
    uci set network.lan.ipaddr='192.168.10.251'
    uci commit network
fi
exit 0
""")
    defaults.chmod(0o755)

def check(build):
    actual = set((build / '.config').read_text().splitlines())
    wanted = [s for s in (RECIPE / 'config.seed').read_text().splitlines() if s.startswith('CONFIG_')]
    missing = [s for s in wanted if s not in actual]
    forbidden = ['luci-app-dockerman', 'dockerd', 'luci-app-samba4', 'luci-app-zerotier', 'luci-app-passwall2']
    missing += [f'Unexpected package {p}' for p in forbidden if f'CONFIG_PACKAGE_{p}=y' in actual]
    if missing:
        raise SystemExit('\n'.join(missing))
    print('Device, filesystem, PassWall and all requested dependencies selected')

def collect(build):
    target = build / 'bin/targets/qualcommax/ipq60xx'
    out = Path(os.environ['GITHUB_WORKSPACE']) / 'artifacts'
    profiles = json.loads((target / 'profiles.json').read_text())
    profile = profiles['profiles'][PROFILE]
    if BOARD not in profile['supported_devices']:
        raise SystemExit('Unexpected board metadata')
    images = [i for i in profile['images'] if i['type'] == 'sysupgrade']
    if len(images) != 1:
        raise SystemExit('Expected exactly one sysupgrade image')
    entry = images[0]
    image = target / entry['name']
    if entry.get('filesystem') != 'squashfs' or digest(image) != entry['sha256']:
        raise SystemExit('Wrong filesystem or profiles.json hash mismatch')
    fwtool = build / 'staging_dir/host/bin/fwtool'
    metadata_file = out / 'image-metadata.json'
    subprocess.run([str(fwtool), '-i', str(metadata_file), str(image)], check=True)
    if BOARD not in json.loads(metadata_file.read_text())['supported_devices']:
        raise SystemExit('Image metadata board mismatch')
    with tarfile.open(image) as archive:
        files = {m.name: m for m in archive.getmembers() if m.isfile()}
        kernels = [m for n, m in files.items() if n.endswith('/kernel')]
        roots = [m for n, m in files.items() if n.endswith('/root')]
        if len(kernels) != 1 or len(roots) != 1:
            raise SystemExit('Missing or ambiguous kernel/root members')
        if not 0 < kernels[0].size <= 6144 * 1024:
            raise SystemExit('Kernel exceeds the observed 6 MiB partition')
        if not 0 < roots[0].size <= 2097152 * 1024:
            raise SystemExit('Root filesystem exceeds the observed 2 GiB partition')
        if archive.extractfile(kernels[0]).read(4) != bytes.fromhex('d00dfeed'):
            raise SystemExit('Expected a FIT kernel')
        if archive.extractfile(roots[0]).read(4) != b'hsqs':
            raise SystemExit('Expected a SquashFS root filesystem')
    manifests = list(target.glob(f'*{PROFILE}*.manifest'))
    if len(manifests) != 1:
        raise SystemExit('Missing device package manifest')
    packages = {line.split()[0] for line in manifests[0].read_text().splitlines() if line.strip()}
    required = {'luci-app-passwall', 'luci-i18n-passwall-zh-cn', 'xray-core', 'sing-box',
                'hysteria', 'kmod-fs-f2fs', 'mkf2fs', 'f2fsck', 'block-mount',
                'libatomic1', 'kmod-tun', 'kmod-inet-diag', 'kmod-netlink-diag',
                'kmod-nft-socket', 'kmod-nft-tproxy', 'ipq-wifi-jdcloud_re-ss-01'}
    if required - packages:
        raise SystemExit(f'Missing installed packages: {required - packages}')
    versions = dict(line.split()[:2] for line in manifests[0].read_text().splitlines() if line.strip())
    if not versions['hysteria'].startswith('2.'):
        raise SystemExit('Expected Hysteria 2')
    if not versions['xray-core'].startswith('26.9.9-'):
        raise SystemExit('Xray must match the tested PassWall-compatible version')
    shutil.copytree(target, out / 'firmware', dirs_exist_ok=True)
    shutil.copytree(build / 'bin/packages', out / 'packages', dirs_exist_ok=True)
    shutil.copyfile(RECIPE / 'README.md', out / 'README.md')
    files = sorted(p for p in out.rglob('*') if p.is_file() and p.name != 'SHA256SUMS')
    (out / 'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.relative_to(out).as_posix()}\n' for p in files))
    print(f'Validated {image.name}; FIT, SquashFS, board metadata, packages and hashes passed')

if __name__ == '__main__':
    {'prepare': prepare, 'check': check, 'collect': collect}[sys.argv[1]](Path(sys.argv[2]).resolve())
