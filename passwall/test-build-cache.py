"""Regression checks for compatibility boundaries of the package-state cache."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('build_cache', Path(__file__).with_name('build-cache.py'))
cache = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cache)


class CacheTests(unittest.TestCase):
    def test_compatibility_boundaries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def write(path, text):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
                return target
            write('.config', 'CONFIG_TARGET_test=y\n')
            write(cache.PASSWALL + 'Makefile', 'LUCI_DEPENDS:=+lua\n')
            ui = write(cache.PASSWALL + 'luasrc/view/update.htm', 'old UI')
            go = write('feeds/packages/lang/golang/golang-values.mk', 'Go version 1')
            core = write('feeds/packages/net/xray-core/Makefile', 'Xray version 1')
            before = cache.fingerprint(root, 'toolchain-a')
            ui.write_text('new UI')
            self.assertEqual(before, cache.fingerprint(root, 'toolchain-a'))
            core.write_text('Xray version 2')
            changed = cache.fingerprint(root, 'toolchain-a')
            self.assertNotEqual(before[0], changed[0])
            self.assertEqual(before[1], changed[1])
            go.write_text('Go version 2')
            self.assertNotEqual(changed[1], cache.fingerprint(root, 'toolchain-a')[1])
            for path in ('.config', cache.PASSWALL + 'Makefile'):
                before = cache.fingerprint(root, 'toolchain-a')
                (root / path).write_text((root / path).read_text() + '# changed\n')
                self.assertNotEqual(before[0], cache.fingerprint(root, 'toolchain-a')[0])
            self.assertNotEqual(cache.fingerprint(root, 'toolchain-a'),
                                cache.fingerprint(root, 'toolchain-b'))
            before = cache.fingerprint(root, 'toolchain-a')
            self.assertEqual(before, cache.fingerprint(root, 'toolchain-a', normalize=True))
            self.assertEqual(int(core.stat().st_mtime), 1_600_000_000)
            self.assertNotEqual(int(ui.stat().st_mtime), 1_600_000_000)
            link = root / 'package/core'
            link.parent.mkdir(exist_ok=True)
            link.symlink_to('../feeds/packages/net/xray-core')
            before = cache.fingerprint(root, 'toolchain-a')
            link.unlink()
            link.symlink_to('../feeds/packages/lang/golang')
            self.assertNotEqual(before[0], cache.fingerprint(root, 'toolchain-a')[0])


if __name__ == '__main__':
    unittest.main()
