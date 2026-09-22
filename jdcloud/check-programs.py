"""Run the ARM64 clients extracted from the validated firmware under QEMU."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

output, work = map(Path, sys.argv[1:3])
work.mkdir(parents=True, exist_ok=True)
images = list(output.rglob('*sysupgrade.bin'))
assert len(images) == 1
with tarfile.open(images[0]) as archive:
    roots = [m for m in archive.getmembers() if m.isfile() and m.name.endswith('/root')]
    assert len(roots) == 1
    with (work / 'root.squashfs').open('wb') as stream:
        shutil.copyfileobj(archive.extractfile(roots[0]), stream)
rootfs = work / 'rootfs'
subprocess.run(['unsquashfs', '-d', str(rootfs), str(work / 'root.squashfs'), 'usr', 'lib'], check=True)
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
assert (rootfs / 'usr/sbin/mkfs.f2fs').exists(), 'F2FS formatter absent'
assert list((rootfs / 'lib/modules').rglob('f2fs.ko')), 'F2FS module absent'
geo_checks = ''
if '--geodata' in sys.argv[3:]:
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
    '\nNative ARM64 version/config checks passed under QEMU. Hardware flashing not tested.\n')
def digest(p):
    with p.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
(output / 'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.relative_to(output).as_posix()}\n'
    for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS'))
print(hysteria, xray, tested)
