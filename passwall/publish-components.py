"""Publish immutable tested binaries, then advance per-device channel manifests."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def gh(*args):
    return subprocess.check_output(['gh', *map(str, args)], text=True)


def main(root):
    repo = os.environ['GITHUB_REPOSITORY']
    if repo != 'epenli/immortalwrt':
        raise SystemExit('Review component download URLs before using a different repository')
    tag = f"passwall-build-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
    assets, channels = [], {}
    for device in ('jdcloud', 'ufi'):
        directories = list(root.glob(f'passwall-apk-{device}-*/components'))
        if len(directories) != 1:
            raise SystemExit(f'Missing or ambiguous validated artifact: {device}')
        directory = directories[0]
        document = json.loads((directory / 'components.json').read_text())
        if document['schema'] != 1 or document['device'] != device:
            raise SystemExit('Component manifest mismatch')
        if set(document['components']) != {'xray', 'sing-box', 'hysteria', 'geoview', 'chinadns-ng'}:
            raise SystemExit('Incomplete component set')
        for component, info in document['components'].items():
            filename = f'{device}-{component}-linux-arm64'
            if info['filename'] != filename:
                raise SystemExit('Unexpected asset path')
            path = directory / filename
            if path.stat().st_size != info['size'] or hashlib.sha256(path.read_bytes()).hexdigest() != info['sha256']:
                raise SystemExit('Component checksum mismatch')
            info['url'] = f'https://github.com/{repo}/releases/download/{tag}/{filename}'
            assets.append(path)
        document['recipe_commit'] = os.environ['GITHUB_SHA']
        document['build'] = tag
        channels[device] = document
    gh('release', 'create', tag, '--repo', repo, '--target', os.environ['GITHUB_SHA'],
       '--draft', '--title', tag, '--notes', 'Validated PassWall component binaries for JDCloud and 4G Dongle. APK bundles are available in the matching Actions run.')
    gh('release', 'upload', tag, '--repo', repo, *assets)
    gh('release', 'edit', tag, '--repo', repo, '--draft=false', '--latest=false')
    for device, document in channels.items():
        channel = f'passwall-components-{device}'
        found = subprocess.run(['gh', 'release', 'view', channel, '--repo', repo],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if found.returncode:
            gh('release', 'create', channel, '--repo', repo, '--target', os.environ['GITHUB_SHA'],
               '--title', f'PassWall components: {device}', '--notes',
               'Version manifest for the existing PassWall component-update buttons.', '--latest=false')
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / 'components.json'
            manifest.write_text(json.dumps(document, indent=2) + '\n')
            gh('release', 'upload', channel, manifest, '--repo', repo, '--clobber')
        print(f'Published {channel} -> {tag}')


if __name__ == '__main__':
    main(Path(sys.argv[1]))
