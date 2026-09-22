"""Validate UFI PassWall packages and execute clients from the actual ext4 image."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

output, work = (Path(p).resolve() for p in sys.argv[1:])
work.mkdir(parents=True, exist_ok=True)
manifest = list((output / 'firmware').glob('*openstick-ufi003*.manifest'))
assert len(manifest) == 1, 'Expected one UFI package manifest'
versions = dict(line.split(' - ', 1) for line in manifest[0].read_text().splitlines() if line.strip())
required = {'luci-app-passwall', 'luci-i18n-passwall-zh-cn', 'hysteria', 'xray-core',
            'sing-box', 'geoview', 'v2ray-geoip', 'v2ray-geosite', 'libatomic1',
            'kmod-tun', 'kmod-nft-socket', 'kmod-nft-tproxy', 'kmod-inet-diag', 'kmod-netlink-diag'}
assert not required - versions.keys(), f'Missing packages: {required - versions.keys()}'
assert versions['hysteria'].startswith('2.7.0-'), versions['hysteria']
assert versions['xray-core'].startswith('26.9.9-'), versions['xray-core']
images = list((output / 'firmware').glob('*ext4-sysupgrade.bin'))
assert len(images) == 1, 'Expected one UFI sysupgrade image'
raw = work / 'root.ext4'
with tarfile.open(images[0]) as archive:
    members = [m for m in archive.getmembers() if m.isfile() and m.name == 'root.ext4.gz']
    assert len(members) == 1, 'Expected one compressed ext4 root'
    with gzip.GzipFile(fileobj=archive.extractfile(members[0])) as src, raw.open('wb') as dst:
        shutil.copyfileobj(src, dst)
rootfs = work / 'rootfs'
rootfs.mkdir()
for directory in ['usr', 'lib']:
    subprocess.run(['debugfs', '-R', f'rdump /{directory} {rootfs}', str(raw)], check=True)
def run(binary, *args):
    return subprocess.check_output(['qemu-aarch64', '-L', str(rootfs),
        str(rootfs / 'usr/bin' / binary), *args], text=True, stderr=subprocess.STDOUT, timeout=90)
hysteria = run('hysteria', 'version')
assert '2.7.0' in hysteria, hysteria
xray = run('xray', 'version')
assert '26.9.9' in xray, xray
# The installed PassWall generator uses these newer configuration fields.
config = {'version': {'min': '26.7.11'},
          'log': {'loglevel': 'error'},
          'dns': {'servers': [{'address': 'tcp://1.1.1.1:53', 'queryStrategy': 'UseIPv4'}]},
          'inbounds': [{'listen': '127.0.0.1', 'port': 15353, 'protocol': 'tunnel',
                        'settings': {'allowedNetwork': 'tcp,udp'}, 'tag': 'dns-in'}],
          'outbounds': [{'protocol': 'dns', 'tag': 'dns-out',
                         'settings': {'rewriteNetwork': 'tcp', 'rewriteAddress': '1.1.1.1',
                                      'rewritePort': 53, 'rules': [{'action': 'hijack', 'qType': '1,28'},
                                                                  {'action': 'direct'}]}}],
          'routing': {'rules': [{'inboundTag': ['dns-in'], 'outboundTag': 'dns-out'}]}}
config_path = work / 'dns-test.json'
config_path.write_text(json.dumps(config))
tested = run('xray', 'run', '-test', '-config', str(config_path))
geo_checks = ''
if True:
    geo_checks += run('geoview', '-version')
    for kind, code in [('geoip', 'cn'), ('geosite', 'disney')]:
        data = rootfs / 'usr/share/v2ray' / (kind + '.dat')
        assert data.is_file() and data.stat().st_size > 0, f'{kind} data absent'
        converted = work / (kind + '-test.srs')
        run('geoview', '-type', kind, '-action', 'convert', '-input', str(data),
            '-list', code, '-output', str(converted))
        assert converted.is_file() and converted.stat().st_size > 0, f'{kind} conversion failed'
        geo_checks += f'{kind}: {code} conversion passed\n'
(output / 'PROGRAM-CHECKS.txt').write_text(hysteria + '\n' + xray + '\n' + tested + '\n' + geo_checks +
    '\nNative ARM64 client and Geo conversion tests passed. Hardware flashing not tested.\n')
def digest(p):
    with p.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
(output / 'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.relative_to(output).as_posix()}\n'
    for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS'))
print(hysteria, xray, tested, geo_checks)
