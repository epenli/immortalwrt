"""Validate preserved JDCloud outputs without rebuilding or modifying images."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile

PROFILE = 'jdcloud_re-ss-01'
BOARD = 'jdcloud,re-ss-01'

def one(root, pattern):
    paths = list(root.rglob(pattern))
    if len(paths) != 1:
        raise ValueError(f'Expected one {pattern}, found {len(paths)}')
    return paths[0]

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def validate(root):
    profiles_file = one(root, 'profiles.json')
    profile = json.loads(profiles_file.read_text())['profiles'][PROFILE]
    assert BOARD in profile['supported_devices'], 'Wrong board'
    images = [i for i in profile['images'] if i['type'] == 'sysupgrade']
    assert len(images) == 1, 'Ambiguous sysupgrade image'
    entry = images[0]
    image = profiles_file.parent / entry['name']
    assert entry['filesystem'] == 'squashfs', 'Wrong filesystem'
    assert digest(image) == entry['sha256'], 'Image hash mismatch'
    with tarfile.open(image) as archive:
        kernels = [m for m in archive.getmembers() if m.isfile() and m.name.endswith('/kernel')]
        roots = [m for m in archive.getmembers() if m.isfile() and m.name.endswith('/root')]
        assert len(kernels) == len(roots) == 1, 'Ambiguous image contents'
        assert 0 < kernels[0].size <= 6144 * 1024, 'Kernel partition overflow'
        assert 0 < roots[0].size <= 2097152 * 1024, 'Root partition overflow'
        assert archive.extractfile(kernels[0]).read(4) == bytes.fromhex('d00dfeed'), 'Not FIT'
        assert archive.extractfile(roots[0]).read(4) == b'hsqs', 'Not SquashFS'
    manifest = one(root, f'*{PROFILE}*.manifest')
    versions = dict(line.split(' - ', 1) for line in manifest.read_text().splitlines() if line.strip())
    required = {'luci-app-passwall', 'luci-i18n-passwall-zh-cn', 'sing-box', 'xray-core',
                'hysteria', 'kmod-fs-f2fs', 'mkf2fs', 'f2fsck', 'block-mount', 'libatomic1',
                'kmod-tun', 'kmod-inet-diag', 'kmod-netlink-diag', 'kmod-nft-socket',
                'kmod-nft-tproxy', 'ipq-wifi-jdcloud_re-ss-01'}
    assert not required - versions.keys(), f'Missing packages: {required - versions.keys()}'
    assert versions['hysteria'].startswith('2.'), 'Not Hysteria 2'
    assert versions['xray-core'].startswith('26.9.9-'), 'Wrong Xray version'
    metadata = one(root, 'image-metadata.json')
    assert BOARD in json.loads(metadata.read_text())['supported_devices'], 'Wrong fwtool board metadata'
    return image, manifest, profiles_file, metadata, versions

def main(root, output):
    image, manifest, profiles, metadata, versions = validate(root)
    output.mkdir(parents=True, exist_ok=True)
    for p in (image, manifest, profiles, metadata):
        shutil.copy2(p, output / p.name)
    for name in ('source.json', 'feeds.conf', 'feed-commits.txt', 'expanded.config', 'diffconfig'):
        shutil.copy2(one(root, name), output / name)
    (output / 'VALIDATION.json').write_text(json.dumps({'image': image.name, 'sha256': digest(image),
        'board': BOARD, 'versions': versions, 'status': 'image-validation-passed',
        'device_flash_verified': False}, indent=2) + '\n')
    (output / 'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.name}\n'
        for p in sorted(output.iterdir()) if p.is_file() and p.name != 'SHA256SUMS'))
    print('Board, image hash, partition bounds, FIT/SquashFS and package versions passed')

if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]))
