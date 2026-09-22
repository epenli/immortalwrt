#!/usr/bin/env python3
"""Bundle a matched Android boot + RAW ext4 image for our RAM-stage upgrader."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile
import tempfile
import importlib.util

_spec = importlib.util.spec_from_file_location('ext4_padding', Path(__file__).with_name('ext4-padding.py'))
_padding = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_padding)


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def pack(boot, root, output, fwtool):
    if root.stat().st_size != 512 * 1024 * 1024:
        raise ValueError('Only a 512 MiB RAW ext4 root image is supported')
    with root.open('rb') as f:
        f.seek(1080)
        if f.read(2) != b'\x53\xef':
            raise ValueError('Root image is not ext4 (do not pass Android sparse data)')
    with boot.open('rb') as f:
        header = f.read(2048)
    if not 2048 <= boot.stat().st_size <= 64 * 1024 * 1024 or header[:8] != b'ANDROID!':
        raise ValueError('Invalid boot image')
    kernel_size, kernel_addr, ramdisk_size, ramdisk_addr, second_size, second_addr, tags_addr, page_size, version = struct.unpack_from('<9I', header, 8)
    if (kernel_addr, ramdisk_size, second_size, tags_addr, page_size, version) != (0x10008000, 0, 0, 0x10000100, 2048, 0):
        raise ValueError('Boot header does not match the tested LK1ST layout')
    if not kernel_size or 2048 + kernel_size > boot.stat().st_size:
        raise ValueError('Truncated boot kernel')
    if b'root=/dev/mmcblk0p14' not in header[64:576].split(b'\0', 1)[0].split():
        raise ValueError('Boot image has unexpected root device')
    # Repair only the known unused-bitmap padding issue on this scratch file.
    # Every other fsck error or change to file data aborts packaging.
    report = _padding.normalize(root)
    output.with_suffix('.repair.json').write_text(json.dumps(report, indent=2) + '\n')
    with tempfile.TemporaryDirectory(prefix='ufi-pack-', dir=output.parent) as tmp:
        tmp = Path(tmp)
        compressed = tmp / 'root.ext4.gz'
        with root.open('rb') as src, compressed.open('wb') as dst:
            with gzip.GzipFile(fileobj=dst, mode='wb', filename='', mtime=0, compresslevel=6) as gz:
                shutil.copyfileobj(src, gz)
        control = f'UFI003-EXT4-1 {boot.stat().st_size} {digest(boot)} {root.stat().st_size} {digest(root)} {digest(compressed)}\n'.encode()
        candidate = tmp / 'sysupgrade.bin'
        with tarfile.open(candidate, 'w', format=tarfile.USTAR_FORMAT) as tar:
            info = tarfile.TarInfo('CONTROL')
            info.size = len(control)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(control))
            for path, name in [(boot, 'boot.img'), (compressed, 'root.ext4.gz')]:
                info = tarfile.TarInfo(name)
                info.size = path.stat().st_size
                info.mode = 0o644
                with path.open('rb') as f:
                    tar.addfile(info, f)
        metadata = tmp / 'metadata.json'
        metadata.write_text(json.dumps({
            'metadata_version': '1.1', 'compat_version': '1.0',
            'supported_devices': ['thwc,ufi001c'],
            'version': {'dist': 'ImmortalWrt', 'version': 'SNAPSHOT',
                        'target': 'msm89xx/msm8916', 'board': 'openstick-ufi003'},
            'ufi_upgrade_format': 'UFI003-EXT4-1',
        }))
        subprocess.run([str(fwtool), '-I', str(metadata), str(candidate)], check=True)
        if candidate.stat().st_size > 160 * 1024 * 1024:
            raise ValueError('Sysupgrade package exceeds the 160 MiB RAM budget')
        candidate.replace(output)
    print(f'Created {output.name}: {output.stat().st_size} bytes; SHA256={digest(output)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boot', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True, help='RAW ext4, not sparse')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fwtool', type=Path, required=True)
    args = parser.parse_args()
    pack(args.boot, args.root, args.output, args.fwtool)
