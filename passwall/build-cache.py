"""Cache only exact-compatible build state; always rebuild the PassWall UI package."""
import hashlib
import json
import os
from pathlib import Path
import sys

SOURCE_PATHS = ('tools', 'toolchain', 'include', 'scripts', 'config', 'target',
                'package', 'feeds', 'rules.mk', 'Makefile', '.config', 'feeds.conf.default')
PASSWALL = 'feeds/luci/applications/luci-app-passwall/'


def fingerprint(root, toolchain, normalize=False):
    digest = hashlib.sha256()
    go = hashlib.sha256()
    digest.update(Path(__file__).read_bytes())
    workflow = Path(__file__).resolve().parents[1] / ".github/workflows/passwall-apk.yml"
    digest.update(workflow.read_bytes())
    digest.update(toolchain.encode())
    go.update(toolchain.encode())
    for name in SOURCE_PATHS:
        base = root / name
        paths = []
        if base.is_dir():
            for directory, dirs, files in os.walk(base, followlinks=False):
                dirs[:] = sorted(d for d in dirs if d not in ('.git', '__pycache__'))
                paths.extend(Path(directory) / f for f in files if f != '.git')
                paths.extend(Path(directory) / d for d in dirs if (Path(directory) / d).is_symlink())
        elif base.exists():
            paths = [base]
        for path in sorted(paths):
            relative = path.relative_to(root).as_posix()
            # UI payload is deliberately excluded, but its dependency/build recipe is not.
            if relative.startswith(PASSWALL) and relative != PASSWALL + 'Makefile':
                continue
            content = (os.fsencode(os.readlink(path)) if path.is_symlink()
                       else path.read_bytes())
            record = (relative.encode() + b'\0' + str(path.lstat().st_mode).encode()
                      + b'\0' + content + b'\0')
            digest.update(record)
            if relative.startswith('feeds/packages/lang/golang/'):
                go.update(record)
            # Fresh checkout timestamps must not invalidate matching make stamps.
            if normalize:
                os.utime(path, (1_600_000_000, 1_600_000_000), follow_symlinks=False)
    return digest.hexdigest(), go.hexdigest()


def main(root, device, toolchain):
    root = root.resolve()
    state, go = fingerprint(root, toolchain, normalize=True)
    values = {'state': f'{device}-passwall-state-v1-{state}',
              'go': f'{device}-passwall-go-v1-{go}'}
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        for key, value in values.items():
            output.write(f'{key}={value}\n')
    (Path(os.environ['GITHUB_WORKSPACE']) / 'artifacts/build-cache-inputs.json').write_text(
        json.dumps(dict(values, toolchain=toolchain), indent=2) + '\n')
    print(json.dumps(values))


if __name__ == '__main__':
    main(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
