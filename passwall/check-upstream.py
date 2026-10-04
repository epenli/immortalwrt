"""Pin newer upstream PassWall versions and retry versions not yet published."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tarfile
import urllib.error
import urllib.request

UPSTREAM = 'Openwrt-Passwall/openwrt-passwall'


def get(url):
    headers = {'User-Agent': 'PassWall-update-check'}
    if url.startswith('https://api.github.com/') and os.environ.get('GH_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GH_TOKEN']
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=90) as response:
        return response.read()


def version(text):
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-r\d+)?', text):
        raise ValueError('Unexpected PassWall version: ' + text)
    return tuple(map(int, text.split('-r')[0].split('.')))


def candidate(current):
    if current['repository'] != UPSTREAM:
        raise ValueError('Unexpected upstream repository')
    commit = json.loads(get(f'https://api.github.com/repos/{UPSTREAM}/commits?per_page=1'))[0]['sha']
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Invalid upstream commit')
    makefile = get(f'https://raw.githubusercontent.com/{UPSTREAM}/{commit}/luci-app-passwall/Makefile').decode()
    match = re.search(r'^PKG_VERSION\s*:?=\s*(\S+)\s*$', makefile, re.M)
    if not match:
        raise ValueError('Upstream Makefile has no version')
    latest = match[1]
    if version(latest) <= version(current['version']):
        return current
    archive = get(f'https://codeload.github.com/{UPSTREAM}/tar.gz/{commit}')
    # Verify the archive contains the same recipe before changing the source pin.
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as source:
        member = f'openwrt-passwall-{commit}/luci-app-passwall/Makefile'
        if source.extractfile(member).read().decode() != makefile:
            raise ValueError('Upstream archive/recipe mismatch')
    return dict(repository=UPSTREAM, commit=commit, version=latest,
                sha256=hashlib.sha256(archive).hexdigest())


def published(repo, device, wanted):
    url = f'https://github.com/{repo}/releases/download/passwall-components-{device}/components.json'
    try:
        document = json.loads(get(url))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise
    app = document.get('passwall', {})
    return (document.get('schema') == 1 and document.get('device') == device
            and version(app.get('version', '0.0.0')) >= version(wanted)
            and {p.get('name') for p in app.get('packages', [])}
            == {'luci-app-passwall', 'luci-i18n-passwall-zh-cn'})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--repository', default='epenli/immortalwrt')
    args = parser.parse_args()
    path = Path(__file__).with_name('source.json')
    current = json.loads(path.read_text())
    selected = candidate(current)
    changed = selected != current
    # A failed build must not permanently suppress retries after source.json advances.
    channels = {device: published(args.repository, device, selected['version'])
                for device in ('jdcloud', 'ufi')}
    build = changed or not all(channels.values())
    if changed and args.write:
        path.write_text(json.dumps(selected, indent=2) + '\n')
    result = dict(changed=changed, build=build, version=selected['version'], channels=channels)
    print(json.dumps(result, ensure_ascii=False))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            output.write(f'build={str(build).lower()}\nchanged={str(changed).lower()}\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
            summary.write(f"PassWall {selected['version']}: " +
                          ('build required' if build else 'already published; compilation skipped') + '\n')


if __name__ == '__main__':
    main()
