import pathlib
import tempfile
import unittest

from rbassist import quarantine


class QuarantineTests(unittest.TestCase):
    def test_merge_quarantine_records_updates_attempts(self) -> None:
        existing = [
            {
                'path': 'C:/Music/a.mp3',
                'reason': 'decode_eof',
                'phase': 'decode',
                'first_seen': '2026-03-01T00:00:00+00:00',
                'last_seen': '2026-03-01T00:00:00+00:00',
                'attempts': 1,
            }
        ]
        new = [
            {
                'path': r'C:\Music\a.mp3',
                'reason': 'decode_eof',
                'phase': 'decode',
                'timestamp': '2026-03-02T00:00:00+00:00',
                'attempts': 1,
            }
        ]
        merged = quarantine.merge_quarantine_records(existing, new)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['attempts'], 2)
        self.assertEqual(merged[0]['last_seen'], '2026-03-02T00:00:00+00:00')

    def test_load_quarantine_paths_dedupes_normalized_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            path = base / 'quarantine.jsonl'
            lines = [
                '{"path": "C:/Music/a.mp3", "reason": "decode_eof"}',
                '{"path": "C:\\\\Music\\\\a.mp3", "reason": "decode_eof"}',
            ]
            path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            loaded = quarantine.load_quarantine_paths(path)
            self.assertEqual(len(loaded), 1)
            self.assertIn('a.mp3', loaded[0])


if __name__ == '__main__':
    unittest.main()
