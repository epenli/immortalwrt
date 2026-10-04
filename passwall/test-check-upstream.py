"""Check update/skip decisions without network or repository mutations."""
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import unittest
from unittest.mock import patch
import urllib.error

spec = importlib.util.spec_from_file_location('check', Path(__file__).with_name('check-upstream.py'))
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class UpdateTests(unittest.TestCase):
    def current(self):
        return dict(repository=check.UPSTREAM, version='26.9.27', commit='a'*40, sha256='b'*64)

    def responses(self, latest):
        makefile = f'PKG_VERSION:={latest}\n'.encode()
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
            entry = tarfile.TarInfo('openwrt-passwall-' + 'c'*40 + '/luci-app-passwall/Makefile')
            entry.size = len(makefile)
            archive.addfile(entry, io.BytesIO(makefile))
        return [json.dumps([{'sha': 'c'*40}]).encode(), makefile, buffer.getvalue()]

    def test_same_or_older_does_not_download_archive(self):
        for release in ('26.9.27', '26.9.16'):
            with patch.object(check, 'get', side_effect=self.responses(release)) as get:
                self.assertEqual(check.candidate(self.current()), self.current())
                self.assertEqual(get.call_count, 2)

    def test_new_version_is_pinned_with_archive_hash(self):
        responses = self.responses('26.10.3')
        with patch.object(check, 'get', side_effect=responses):
            result = check.candidate(self.current())
        self.assertEqual(result['version'], '26.10.3')
        self.assertEqual(result['commit'], 'c'*40)
        self.assertEqual(result['sha256'], check.hashlib.sha256(responses[2]).hexdigest())

    def test_mismatched_archive_is_rejected(self):
        responses = self.responses('26.10.3')
        responses[2] = self.responses('26.9.27')[2]
        with patch.object(check, 'get', side_effect=responses), self.assertRaises(ValueError):
            check.candidate(self.current())

    def test_unpublished_or_failed_version_is_retried(self):
        doc = dict(schema=1, device='jdcloud', passwall=dict(version='26.9.27-r1', packages=[
            {'name':'luci-app-passwall'}, {'name':'luci-i18n-passwall-zh-cn'}]))
        with patch.object(check, 'get', return_value=json.dumps(doc).encode()):
            self.assertTrue(check.published('example/repo', 'jdcloud', '26.9.27'))
            self.assertFalse(check.published('example/repo', 'jdcloud', '26.10.3'))
            self.assertFalse(check.published('example/repo', 'ufi', '26.9.27'))
        with patch.object(check, 'get', side_effect=urllib.error.HTTPError('url',404,'missing',{},None)):
            self.assertFalse(check.published('example/repo', 'jdcloud', '26.10.3'))
        with patch.object(check, 'get', side_effect=urllib.error.HTTPError('url',403,'denied',{},None)):
            with self.assertRaises(urllib.error.HTTPError):
                check.published('example/repo', 'jdcloud', '26.10.3')


if __name__ == '__main__':
    unittest.main()
