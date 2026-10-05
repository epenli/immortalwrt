"""Offline adapter regressions; optionally exercise the checksum-pinned source archive."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

RECIPE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('install_source', RECIPE / 'install-source.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
ARCHIVE = Path(sys.argv.pop()).resolve() if len(sys.argv) == 2 and sys.argv[1].endswith('.tar.gz') else None


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = self.root / 'usr/lib/lua/luci'
        for directory in ('passwall', 'controller', 'view/passwall/app_update', 'model/cbi/passwall/client'):
            (self.base / directory).mkdir(parents=True)
        (self.base / 'passwall/api.lua').write_text('function to_check(arch, app_name) end\nfunction to_move(app_name,file) end\n')
        self.controller = self.base / 'controller/passwall.lua'
        self.template = self.base / 'view/passwall/app_update/app_version.htm'
        self.page = self.base / 'model/cbi/passwall/client/app_update.lua'
        self.page.write_text('-- keep user page content\n')
        fixture = RECIPE / 'tests/fixtures/26.10.4'
        shutil.copyfile(fixture / 'controller.lua', self.controller)
        shutil.copyfile(fixture / 'app_version.htm', self.template)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_modern_route_and_browser_behavior(self):
        adapter.install(self.root, live=True)
        controller = self.controller.read_text()
        self.assertEqual(controller.count('post("app_install")'), 1)
        self.assertNotIn('"update_" .. appname}, call("app_update")', controller)
        self.assertEqual(controller.count('function app_install()'), 1)
        self.assertIn('http_write_json(api.install_self())', controller)
        self.assertEqual(self.page.read_text(), '-- keep user page content\n')
        subprocess.run(['node', str(RECIPE / 'test-update-template.js'), str(self.template)], check=True)
        before = self.snapshot()
        adapter.install(self.root, live=True)
        self.assertEqual(before, self.snapshot())

    def test_legacy_and_previously_patched_live_root(self):
        self.controller.write_text('\tentry({"admin", "services", appname, "check_passwall"}, call("app_check")).leaf = true\n')
        self.template.write_text('\t\t// Download file\n')
        adapter.install(self.root, live=True)
        self.assertIn('post("app_install")', self.controller.read_text())
        self.assertIn('removePageNotice();', self.template.read_text())
        before = self.snapshot()
        adapter.install(self.root, live=True)
        self.assertEqual(before, self.snapshot())

    def test_unknown_and_duplicate_routes_rejected(self):
        for value in ('-- changed route', self.controller.read_text() * 2):
            with self.subTest(value=value[:30]):
                self.controller.write_text(value)
                with self.assertRaisesRegex(SystemExit, 'Unexpected PassWall controller'):
                    adapter.install(self.root, live=True)

    def test_unknown_and_duplicate_template_rejected(self):
        for value in ('-- changed template', self.template.read_text() * 2):
            with self.subTest(value=value[:30]):
                self.template.write_text(value)
                with self.assertRaisesRegex(SystemExit, 'Unexpected PassWall update template'):
                    adapter.install(self.root, live=True)
                self.assertNotIn('post("app_install")', self.controller.read_text())

    @unittest.skipUnless(ARCHIVE, 'pass pinned .tar.gz to run source archive integration')
    def test_pinned_archive_for_both_recipe_targets(self):
        pin = json.loads((RECIPE / 'source.json').read_text())
        self.assertEqual(hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(), pin['sha256'])
        for target, entrypoint in [('jdcloud', 'jdcloud/build.py'), ('ufi', 'scripts/prepare.py')]:
            with self.subTest(target=target):
                # Both real recipe entrypoints invoke this common installer.
                self.assertIn('passwall/install-source.py', (RECIPE.parent / entrypoint).read_text())
                root = self.root / target
                package = root / 'feeds/luci/applications/luci-app-passwall'
                package.mkdir(parents=True)
                (root / 'dl').mkdir()
                archive = root / 'dl' / ('passwall-' + pin['commit'] + '.tar.gz')
                shutil.copyfile(ARCHIVE, archive)
                adapter.install(root)
                self.assertIn('PKG_VERSION:=' + pin['version'], (package / 'Makefile').read_text())
                subprocess.run(['node', str(RECIPE / 'test-update-template.js'), str(package / 'luasrc/view/passwall/app_update/app_version.htm')], check=True)
                before = {str(p.relative_to(package)): p.read_bytes() for p in package.rglob('*') if p.is_file()}
                adapter.install(root)
                self.assertEqual(before, {str(p.relative_to(package)): p.read_bytes() for p in package.rglob('*') if p.is_file()})
                archive.write_bytes(b'bad archive')
                with self.assertRaisesRegex(SystemExit, 'checksum mismatch'):
                    adapter.install(root)


if __name__ == '__main__':
    unittest.main()
