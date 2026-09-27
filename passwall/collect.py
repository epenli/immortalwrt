"""Collect APKs, check architecture, and execute the packaged ARM64 clients."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

REQUIRED = {
    'luci-app-passwall', 'luci-i18n-passwall-zh-cn', 'hysteria', 'sing-box',
    'xray-core', 'geoview', 'v2ray-geoip', 'v2ray-geosite', 'chinadns-ng',
    'dns2socks', 'ipt2socks', 'microsocks', 'tcping', 'resolveip',
}


def run(*args):
    return subprocess.check_output([str(a) for a in args], text=True,
                                   stderr=subprocess.STDOUT, timeout=180)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main(build, output, device):
    build, output = build.resolve(), output.resolve()
    expected = {'jdcloud': 'qualcommax_ipq60xx', 'ufi': 'msm89xx_msm8916'}[device]
    config = (build / '.config').read_text()
    if f'CONFIG_TARGET_{expected}=y' not in config or 'CONFIG_USE_APK=y' not in config:
        raise SystemExit('Wrong device or non-APK configuration')
    architecture = re.search(r'^CONFIG_TARGET_ARCH_PACKAGES="([^"]+)"$', config, re.M)
    if not architecture:
        raise SystemExit('Missing package architecture')
    architecture = architecture[1]
    apk = build / 'staging_dir/host/bin/apk'
    candidates = sorted((build / 'bin/packages').rglob('*.apk'))
    for directory in (build / 'bin/targets').glob('*/*/packages'):
        candidates.extend(sorted(directory.glob('*.apk')))
    if not candidates:
        raise SystemExit('No compiled APKs')
    records, seen = [], {}
    roots = {name: output / name for name in ('packages', 'kernel-packages')}
    for directory in roots.values():
        directory.mkdir(parents=True, exist_ok=True)
    for path in candidates:
        info = json.loads(run(apk, 'adbdump', '--format', 'json', path))['info']
        name, version, arch = (info[key] for key in ('name', 'version', 'arch'))
        if arch not in (architecture, 'all', 'noarch'):
            raise SystemExit(f'Foreign architecture: {name} {arch}, expected {architecture}')
        checksum = digest(path)
        if name in seen:
            if seen[name] != (version, checksum):
                raise SystemExit(f'Ambiguous package: {name}')
            continue
        seen[name] = (version, checksum)
        run(apk, 'verify', '--allow-untrusted', path)
        group = 'kernel-packages' if name == 'kernel' or name.startswith('kmod-') else 'packages'
        target = roots[group] / path.name
        shutil.copyfile(path, target)
        records.append(dict(name=name, version=version, arch=arch,
                            file=str(target.relative_to(output)), sha256=checksum,
                            depends=info.get('depends', [])))
    missing = REQUIRED - seen.keys()
    if missing:
        raise SystemExit(f'Missing required packages: {sorted(missing)}')
    if not seen['hysteria'][0].startswith('2.'):
        raise SystemExit('Expected Hysteria 2')
    if not seen['xray-core'][0].startswith('26.9.9-'):
        raise SystemExit('Missing the firmware Xray compatibility backport')
    for directory in roots.values():
        files = sorted(directory.glob('*.apk'))
        if files:
            run(apk, 'mkndx', '--allow-untrusted', '--output', directory / 'packages.adb', *files)
    # Extract actual APK contents, without executing installation scripts.
    root = build / 'passwall-apk-check'
    root.mkdir()
    run(apk, 'extract', '--allow-untrusted', '--force-overwrite', '--no-chown',
        '--destination', root, *sorted(roots['packages'].glob('*.apk')))
    checks = []
    for binary, args in [('hysteria', ['version']), ('sing-box', ['version']),
                         ('xray', ['version']), ('geoview', ['-version'])]:
        result = run('qemu-aarch64', '-L', root, root / 'usr/bin' / binary, *args)
        checks.append(f'{binary}:\n{result}')
    for kind, code in [('geoip', 'cn'), ('geosite', 'disney')]:
        data = root / 'usr/share/v2ray' / f'{kind}.dat'
        converted = build / f'passwall-{kind}-test.srs'
        run('qemu-aarch64', '-L', root, root / 'usr/bin/geoview',
            '-type', kind, '-action', 'convert', '-input', data,
            '-list', code, '-output', converted)
        if not converted.is_file() or not converted.stat().st_size:
            raise SystemExit(f'Geo conversion failed: {kind}')
        checks.append(f'{kind}: {code} conversion passed')
    public_key = build / 'public-key.pem'
    if public_key.exists():
        shutil.copyfile(public_key, output / 'build-public-key.pem')
    shutil.copyfile(Path(__file__).with_name('README.md'), output / 'README.md')
    metadata = dict(device=device, architecture=architecture,
                    recipe_commit=os.environ.get('GITHUB_SHA'),
                    source=json.loads((output / 'source.json').read_text()),
                    packages=sorted(records, key=lambda p: p['name']))
    (output / 'manifest.json').write_text(json.dumps(metadata, indent=2) + '\n')
    (output / 'PROGRAM-CHECKS.txt').write_text('\n'.join(checks) + '\n')
    (output / 'SHA256SUMS').write_text(''.join(
        f'{digest(p)}  {p.relative_to(output)}\n' for p in sorted(output.rglob('*'))
        if p.is_file() and p.name != 'SHA256SUMS'))
    print(f'{device}: {len(records)} APKs verified; architecture={architecture}')


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
