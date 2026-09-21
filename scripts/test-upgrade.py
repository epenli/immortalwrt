#!/usr/bin/env python3
"""Exercise archive rejection and write-failure handling without block devices."""
import gzip
import hashlib
import io
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile
import tempfile

PLATFORM = Path(__file__).resolve().parents[1] / 'files/lib/upgrade/platform.sh'
SHELL = os.environ.get('UFI_TEST_SHELL', 'bash')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def archive(path, control, boot, root, extra=False, symlink=False):
    with tarfile.open(path, 'w', format=tarfile.USTAR_FORMAT) as t:
        for name, data in [('CONTROL', control.encode()), ('boot.img', boot), ('root.ext4.gz', root)]:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            if symlink and name == 'boot.img':
                info.type = tarfile.SYMTYPE
                info.linkname = '/dev/mmcblk0p14'
                info.size = 0
                t.addfile(info)
            else:
                t.addfile(info, io.BytesIO(data))
        if extra:
            t.addfile(tarfile.TarInfo('boot.img'))


def main():
    with tempfile.TemporaryDirectory(prefix='ufi-upgrade-test-') as tmp:
        tmp = Path(tmp)
        platform = tmp / 'platform.sh'
        shutil.copyfile(PLATFORM, platform)

        def run(code, ok=True):
            p = subprocess.run([SHELL, '-c', '. ./platform.sh\n' + code], cwd=tmp,
                               text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if (p.returncode == 0) != ok:
                raise AssertionError(f'Unexpected exit {p.returncode}\n{p.stdout}\n{p.stderr}')
            return p

        # A small compressed archive expands to the actual supported 512 MiB.
        boot = b'ANDROID!' + b'B' * 4088
        h = hashlib.sha256()
        root_file = tmp / 'root.gz'
        block = bytes(1024 * 1024)
        with gzip.open(root_file, 'wb') as f:
            for _ in range(512):
                f.write(block)
                h.update(block)
        root = root_file.read_bytes()
        control = f'UFI003-EXT4-1 {len(boot)} {sha(boot)} 536870912 {h.hexdigest()} {sha(root)}\n'
        archive(tmp / 'valid.bin', control, boot, root)
        # fwtool format is covered by the real packer's CLI invocation in CI.
        # Here it is stubbed to isolate tar/gzip/hash validation and RAM usage.
        prefix = 'fwtool() { return 0; }\nufi_full_check=1\n'
        run(prefix + 'ufi_check_package valid.bin')
        for name, args in {
            'bad-boot': (control, b'BADBOOT!' + boot[8:], root),
            'truncated-gzip': (control.replace(sha(root), sha(root[:-8])), boot, root[:-8]),
            'wrong-raw-size': (control.replace('536870912', '536870913'), boot, root),
            'wrong-raw-sha': (control.replace(h.hexdigest(), '0' * 64), boot, root),
        }.items():
            archive(tmp / (name + '.bin'), *args)
            run(prefix + f'ufi_check_package {name}.bin', ok=False)
        for name, kw in [('duplicate', {'extra': True}), ('symlink', {'symlink': True})]:
            archive(tmp / (name + '.bin'), control, boot, root, **kw)
            run(prefix + f'ufi_check_package {name}.bin', ok=False)
        run('ufi_check_package valid.bin', ok=False)  # absent metadata/tool
        # A normal host must never pass the real hardware / RAM stage guards.
        run('ufi_check_layout', ok=False)
        run('ufi_check_ram_stage', ok=False)

        # Exercise the real platform_do_upgrade in a shell whose entire I/O
        # boundary maps to disposable ordinary files. Never open a /dev path.
        payload = b'R' * 4096
        (tmp / 'payload.gz').write_bytes(gzip.compress(payload))
        (tmp / 'boot.payload').write_bytes(boot)
        (tmp / 'control').write_text(f'UFI003-EXT4-1 {len(boot)} {sha(boot)} {len(payload)} {sha(payload)} unused\n')
        with tarfile.open(tmp / 'backup.tgz', 'w:gz') as t:
            t.addfile(tarfile.TarInfo('etc/config/network'))
        harness = r'''
ufi_check_layout() { return 0; }
ufi_check_package() { return 0; }
ufi_check_ram_stage() { return 0; }
ufi_member() {
    case "$2" in
        CONTROL) cat control;;
        root.ext4.gz) cat payload.gz;;
        boot.img) cat boot.payload;;
        *) return 99;;
    esac
}
dd() {
    local arg target='' fail=0
    for arg in "$@"; do
        case "$arg" in
            of=/dev/mmcblk0p14) target=root.written; [ "$FAIL_AT" = root ] && fail=1;;
            of=/dev/mmcblk0p12) target=boot.written; [ "$FAIL_AT" = boot ] && fail=1;;
            of=*) echo 'Unexpected output path' >&2; return 99;;
        esac
    done
    [ -n "$target" ] || return 99
    echo "$target" >> events
    cat > "$target"
    [ "$fail" = 0 ]
}
head() {
    case "$3" in
        /dev/mmcblk0p14) [ "$FAIL_AT" = readback ] && echo broken || cat root.written;;
        /dev/mmcblk0p12) cat boot.written;;
        *) return 99;;
    esac
}
mount() { echo mount >> events; [ "$FAIL_AT" != config ]; }
umount() { echo umount >> events; return 0; }
mkdir() { echo mkdir >> events; return 0; }
rmdir() { return 0; }
rm() { echo rm >> events; return 0; }
cp() { echo backup >> events; return 0; }
touch() { echo marker >> events; return 0; }
sync() { echo sync >> events; return 0; }
'''
        for fail, backup in [('', False), ('', True), ('root', False), ('readback', False), ('boot', False), ('config', True)]:
            for name in ['events', 'boot.written', 'root.written']:
                (tmp / name).unlink(missing_ok=True)
            p = run(harness + f'\nFAIL_AT={shlex.quote(fail)}\nUPGRADE_BACKUP={"backup.tgz" if backup else ""}\n'
                    'platform_do_upgrade fixture\necho COMPLETED\n', ok=not fail)
            events = (tmp / 'events').read_text().splitlines()
            if fail:
                assert 'COMPLETED' not in p.stdout, (fail, p.stdout)
                if fail != 'boot':
                    assert 'boot.written' not in events, (fail, events)
            else:
                assert (tmp / 'root.written').read_bytes() == payload
                assert (tmp / 'boot.written').read_bytes() == boot
                assert events.index('root.written') < events.index('boot.written')
                if backup:
                    assert events.index('umount') < events.index('boot.written')
                    assert 'backup' in events and 'marker' in events
        print('PASS: package validation, unsafe stage rejection, write/readback/config failures, write ordering')


if __name__ == '__main__':
    main()
