"""Exercise recovery decisions without changing real wireless interfaces."""
import os
from pathlib import Path
import subprocess
import tempfile
from ufi_features import install, TRIGGERS

scripts = Path(__file__).resolve().parent
mock = r'''
sleep() { [ "$1" != 600 ] || echo cooldown >> "$TEST_LOG"; return 0; }
jsonfilter() { cat; }
logger() { :; }
iw() { [ "$SCENARIO" = failed ] || echo 'Connected to test'; }
ubus() {
 case "$*" in
 *SCAN_RESULTS*) printf '%s\n' 'bssid / frequency / signal level / flags / ssid'; [ "$SCENARIO" != populated ] || echo 'test-ap';;
 *STATUS*) [ "$SCENARIO" = healthy ] && echo 'wpa_state=COMPLETED' || echo 'wpa_state=SCANNING';;
 *network.wireless*) [ "$SCENARIO" = disabled ] && echo false || echo true;;
 *get_status*) [ "$SCENARIO" = noap ] && return 1; echo ENABLED;;
 *apsta_state*) echo "$*" >> "$TEST_LOG";;
 esac
 return 0
}
'''
source = (scripts / 'ufi-wifi-recovery.sh').read_text()
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root / '.config').touch()
    install(root)
    for path in (root / 'files').rglob('*'):
        if path.is_file() and path.read_text().startswith('#!/bin/sh'):
            subprocess.run(['sh', '-n', str(path)], check=True)
            assert path.stat().st_mode & 0o111
    assert len(list((root / 'files/www/luci-static/resources/view/system/led-trigger').glob('*.js'))) == len(TRIGGERS)
    for scenario, ticks in [('healthy', 5), ('populated', 5), ('disabled', 5),
                            ('noap', 5), ('stuck', 3), ('stuck', 5), ('failed', 5)]:
        log = root / f'{scenario}-{ticks}.log'
        bounded = source.replace('while sleep 30; do',
                                 'for test_tick in ' + ' '.join(map(str, range(ticks))) + '; do')
        subprocess.run(['sh'], input=mock + bounded, text=True, check=True,
                       env=dict(os.environ, SCENARIO=scenario, TEST_LOG=str(log)))
        events = log.read_text() if log.exists() else ''
        expected = int(scenario in ('stuck', 'failed') and ticks >= 4)
        assert events.count('"up":false') == expected, (scenario, events)
        assert events.count('"up":true') == expected, (scenario, events)
        assert events.count('cooldown') == expected, (scenario, events)
        print(f'{scenario}, {ticks} samples: passed')
print('UFI feature generation, recovery thresholds and AP restoration passed.')
