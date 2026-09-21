#!/usr/bin/env python3
"""Check the expanded Kconfig, not merely the input seed."""
import pathlib
import sys

root = pathlib.Path(__file__).resolve().parents[1]
actual = pathlib.Path(sys.argv[1]).read_text().splitlines()
enabled = set(actual)
required = [s for s in (root / 'config.seed').read_text().splitlines() if s.endswith('=y')]
missing = [s for s in required if s not in enabled]
forbidden = ['dockerd', 'luci-app-alist', 'luci-app-passwall2', 'samba4-server',
             'zerotier', 'luci-app-ddns-go', 'ttyd']
unexpected = [p for p in forbidden if f'CONFIG_PACKAGE_{p}=y' in enabled]
if missing or unexpected:
    raise SystemExit(f'Configuration rejected. Missing: {missing}; unexpected: {unexpected}')
print('Expanded configuration includes all required hardware and LuCI packages.')
