#!/usr/bin/env python3
"""Validate and produce consistent Fastboot and sysupgrade image variants."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

spec = importlib.util.spec_from_file_location('pack_upgrade', Path(__file__).with_name('pack-upgrade.py'))
packer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packer)


def finalize(firmware, fwtool):
    def one(pattern):
        matches = list(firmware.glob(pattern))
        if len(matches) != 1:
            raise ValueError(f'Expected one {pattern}: {matches}')
        return matches[0]
    boot = one('*-openstick-ufi003-ext4-boot.img')
    sparse = one('*-openstick-ufi003-ext4-system.img')
    with tempfile.TemporaryDirectory(prefix='ufi-finalize-', dir=firmware.parent) as tmp:
        tmp = Path(tmp)
        metadata = tmp / 'metadata.json'
        subprocess.run([str(fwtool), '-i', str(metadata), str(sparse)], check=True)
        meta = json.loads(metadata.read_text())
        if 'openstick-ufi003' not in meta.get('supported_devices', []):
            raise ValueError('Original system metadata has a different board')
        raw = tmp / 'root.ext4'
        subprocess.run(['simg2img', str(sparse), str(raw)], check=True)
        packer.pack(boot, raw, firmware / 'immortalwrt-openstick-ufi003-ext4-sysupgrade.bin', fwtool)
        regenerated = tmp / 'system.img'
        subprocess.run(['img2simg', str(raw), str(regenerated)], check=True)
        subprocess.run([str(fwtool), '-I', str(metadata), str(regenerated)], check=True)
        roundtrip = tmp / 'roundtrip.ext4'
        subprocess.run(['simg2img', str(regenerated), str(roundtrip)], check=True)
        if packer.digest(raw) != packer.digest(roundtrip):
            raise ValueError('Regenerated Fastboot image differs from sysupgrade rootfs')
        subprocess.run(['e2fsck', '-fn', str(roundtrip)], check=True)
        regenerated.replace(sparse)
        with sparse.open('rb') as src, sparse.with_suffix('.img.gz').open('wb') as dst:
            with gzip.GzipFile(filename='', fileobj=dst, mode='wb', mtime=0) as gz:
                shutil.copyfileobj(src, gz)
    # Update upstream index entries affected by normalization.
    profiles = firmware / 'profiles.json'
    if profiles.exists():
        data = json.loads(profiles.read_text())
        for profile in data.get('profiles', {}).values():
            for image in profile.get('images', []):
                path = firmware / image['name']
                if path.is_file():
                    image['sha256'] = packer.digest(path)
                    if 'size' in image:
                        image['size'] = path.stat().st_size
        profiles.write_text(json.dumps(data, indent=2) + '\n')
    for checksum in firmware.glob('*.sha256sum'):
        image = checksum.with_suffix('')
        if image.is_file():
            checksum.write_text(packer.digest(image) + '\n')
    paths = sorted(p for p in firmware.iterdir() if p.is_file() and p.name != 'sha256sums')
    (firmware / 'sha256sums').write_text(''.join(f'{packer.digest(p)}  {p.name}\n' for p in paths))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('firmware', type=Path)
    parser.add_argument('fwtool', type=Path)
    args = parser.parse_args()
    finalize(args.firmware.resolve(), args.fwtool.resolve())
