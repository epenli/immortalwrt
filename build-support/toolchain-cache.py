"""Fingerprint toolchain inputs and normalize pinned build-recipe timestamps."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def configuration(text):
    # Package-only changes can reuse the compiler. These packages also select host tools.
    host_selectors = {'CONFIG_PACKAGE_kmod-b43', 'CONFIG_BRCMSMAC_USE_FW_FROM_WL'}
    return sorted(line for line in text.splitlines()
                  if line.startswith('CONFIG_') and
                  (not line.startswith('CONFIG_PACKAGE_') or line.split('=', 1)[0] in host_selectors))


def main(root, family):
    root = root.resolve()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args])
    paths = ['tools', 'toolchain', 'include', 'scripts', 'config', 'target/linux', 'rules.mk', 'Makefile']
    tracked = git('ls-files', '-z', '--', *paths).split(b'\0')
    content = hashlib.sha256()
    epoch = int(git('show', '-s', '--format=%ct', 'HEAD'))
    for entry in sorted(x for x in tracked if x):
        path = root / os.fsdecode(entry)
        content.update(entry + b'\0')
        content.update(os.fsencode(os.readlink(path)) if path.is_symlink() else path.read_bytes())
        content.update(b'\0')
        # A fresh checkout must not make cached build stamps appear obsolete.
        os.utime(path, (epoch, epoch), follow_symlinks=False)
    host = subprocess.check_output(['dpkg-query', '-W', '-f=${Package}=${Version}\n',
        'gcc', 'g++', 'binutils', 'libc6', 'libc6-dev', 'libstdc++6', 'make',
        'cmake', 'python3', 'libssl-dev', 'zlib1g-dev', 'libncurses-dev'], text=True)
    inputs = dict(schema=1, helper_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        family=family, build_dir=str(root),
        source=git('rev-parse', 'HEAD').decode().strip(), recipe_hash=content.hexdigest(),
        config=configuration((root / '.config').read_text()), host_packages=host,
        runner_os=os.environ.get('RUNNER_OS'), runner_arch=os.environ.get('RUNNER_ARCH'),
        image_os=os.environ.get('ImageOS'))
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    key = f'{family}-toolchain-v1-{digest}'
    with open(os.environ['GITHUB_OUTPUT'], 'a') as out:
        out.write(f'key={key}\n')
    output = Path(os.environ['GITHUB_WORKSPACE']) / 'artifacts/toolchain-cache-inputs.json'
    output.write_text(json.dumps(inputs, indent=2) + '\n')
    print(f'Toolchain cache key: {key}')


if __name__ == '__main__':
    main(Path(sys.argv[1]), sys.argv[2])
