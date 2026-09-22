#!/usr/bin/env python3
"""Regression checks on generated regular ext4 files, never block devices."""
import importlib.util
from pathlib import Path
import struct
import subprocess
import tempfile

spec = importlib.util.spec_from_file_location('padding', Path(__file__).with_name('ext4-padding.py'))
padding = importlib.util.module_from_spec(spec)
spec.loader.exec_module(padding)
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp) / 'fixture.ext4'
    with root.open('wb') as f:
        f.truncate(64 * 1024 * 1024)
    subprocess.run(['mke2fs', '-q', '-F', '-t', 'ext4', '-b', '4096',
                    '-O', '^metadata_csum,^64bit,^uninit_bg', str(root)], check=True)
    assert not padding.normalize(root)['repaired']
    with root.open('r+b') as f:
        f.seek(1024 + 40)
        ipg = struct.unpack('<I', f.read(4))[0]
        f.seek(4096 + 4)
        bitmap = struct.unpack('<I', f.read(4))[0]
        assert 0 < ipg < 32768 and ipg % 8 == 0
        f.seek(bitmap * 4096 + ipg // 8)
        assert f.read(1) == b'\xff'
        f.seek(-1, 1)
        f.write(b'\x00')
    assert padding.normalize(root)['repaired']
    assert not padding.normalize(root)['repaired']
    with root.open('r+b') as f:
        f.seek(1024 + 56)
        f.write(b'\0\0')
    before = root.read_bytes()
    try:
        padding.normalize(root)
        raise AssertionError('Corrupt superblock was accepted')
    except ValueError:
        assert root.read_bytes() == before
    print('PASS: clean image, known padding repair, idempotence, unrelated corruption rejected unchanged')
