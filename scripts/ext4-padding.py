"""Repair ONLY inode-bitmap padding in a disposable regular image file."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import tempfile


def check(path, mode):
    result = subprocess.run(['e2fsck', mode, str(path)], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            env={**os.environ, 'LC_ALL': 'C'})
    print(result.stdout, flush=True)
    return result


def normalize(path):
    path = Path(path)
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('Only a disposable regular image file may be repaired')
    before = check(path, '-fn')
    if before.returncode == 0:
        return {'repaired': False, 'changed_bytes': 0}
    allowed = [r'e2fsck .+', r'Pass [1-5]: .+',
               r'Padding at end of inode bitmap is not set\. Fix\? no',
               r'.+: \*+ WARNING: Filesystem still has errors \*+',
               r'.+: \d+/\d+ files \([0-9.]+% non-contiguous\), \d+/\d+ blocks']
    lines = [s.strip() for s in before.stdout.splitlines() if s.strip()]
    if before.returncode != 4 or not any(s.startswith('Padding at end of inode bitmap') for s in lines):
        raise ValueError('Filesystem error is not the known inode-bitmap padding issue')
    if any(not any(re.fullmatch(pattern, line) for pattern in allowed) for line in lines):
        raise ValueError('Additional fsck diagnostics require manual review')
    with path.open('rb') as f:
        f.seek(1024)
        sb = f.read(1024)
        if sb[56:58] != b'\x53\xef':
            raise ValueError('Invalid ext4 superblock')
        block_size = 1024 << struct.unpack_from('<I', sb, 24)[0]
        blocks = struct.unpack_from('<I', sb, 4)[0]
        first = struct.unpack_from('<I', sb, 20)[0]
        bpg = struct.unpack_from('<I', sb, 32)[0]
        ipg = struct.unpack_from('<I', sb, 40)[0]
        incompat, ro_compat = struct.unpack_from('<II', sb, 96)
        if block_size != 4096 or incompat & (0x80 | 0x10) or ro_compat & (0x10 | 0x400):
            raise ValueError('Unexpected ext4 layout/checksums; review before repair')
        if not bpg or not ipg or ipg % 8 or ipg >= block_size * 8:
            raise ValueError('Unexpected bitmap geometry')
        groups = (blocks - first + bpg - 1) // bpg
        padding = []
        for group in range(groups):
            f.seek((first + 1) * block_size + group * 32 + 4)
            bitmap = struct.unpack('<I', f.read(4))[0] * block_size
            if not 0 < bitmap < path.stat().st_size - block_size:
                raise ValueError('Bitmap lies outside image')
            padding.append((bitmap + ipg // 8, bitmap + block_size))
    # Standard fsck timestamps, mount count, state and superblock checksum only.
    sb_fields = [(1024 + a, 1024 + b) for a, b in [(48, 54), (58, 60), (64, 68), (1020, 1024)]]
    with tempfile.TemporaryDirectory(prefix='ext4-repair-', dir=path.parent) as tmp:
        candidate = Path(tmp) / 'root.ext4'
        shutil.copyfile(path, candidate)
        repair = check(candidate, '-fp')
        if repair.returncode not in (0, 1) or check(candidate, '-fn').returncode != 0:
            raise ValueError('Repair did not yield a clean filesystem')
        changed = 0
        changed_blocks = []
        with path.open('rb') as old, candidate.open('rb') as new:
            offset = 0
            while chunk := old.read(4096):
                updated = new.read(len(chunk))
                if len(updated) != len(chunk):
                    raise ValueError('Repair changed image length')
                if chunk != updated:
                    changed_blocks.append(offset // 4096)
                    for i, (a, b) in enumerate(zip(chunk, updated)):
                        if a == b:
                            continue
                        pos = offset + i
                        if not (any(start <= pos < end for start, end in sb_fields) or
                                (b == 255 and any(start <= pos < end for start, end in padding))):
                            raise ValueError(f'Repair changed non-padding data at byte {pos}')
                        changed += 1
                offset += len(chunk)
            if new.read(1):
                raise ValueError('Repair changed image length')
        candidate.replace(path)
    return {'repaired': True, 'changed_bytes': changed, 'changed_blocks': changed_blocks,
            'permitted_changes': 'inode bitmap padding and fsck superblock bookkeeping only'}
