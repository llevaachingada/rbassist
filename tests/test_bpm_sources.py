from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase, mock

from rbassist import bpm_sources as bs


class _Query:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _FakeDb:
    def __init__(self, rows):
        self.rows = list(rows)
        self.closed = False

    def get_content(self):
        return _Query(self.rows)

    def close(self):
        self.closed = True


class BpmSourceTests(TestCase):
    def setUp(self) -> None:
        bs.clear_rekordbox_bpm_cache()

    def tearDown(self) -> None:
        bs.clear_rekordbox_bpm_cache()

    def test_normalize_rekordbox_bpm_scales_hundredths(self) -> None:
        self.assertEqual(bs.normalize_rekordbox_bpm(12800), 128.0)
        self.assertEqual(bs.normalize_rekordbox_bpm(126.99), 126.99)
        self.assertIsNone(bs.normalize_rekordbox_bpm(0))

    def test_load_rekordbox_bpm_map_reads_db_rows(self) -> None:
        rows = [
            SimpleNamespace(FolderPath="c:/music/track one.flac", BPM=12800),
            SimpleNamespace(FolderPath="C:/Music/Track Two.flac", BPM=126.99),
            SimpleNamespace(FolderPath="C:/Music/Ignore Zero.flac", BPM=0),
        ]
        with mock.patch.object(bs, "Rekordbox6Database", lambda: _FakeDb(rows)):
            mapping = bs.load_rekordbox_bpm_map()

        self.assertEqual(mapping["C:/music/track one.flac"], 128.0)
        self.assertEqual(mapping["C:/Music/Track Two.flac"], 126.99)
        self.assertNotIn("C:/Music/Ignore Zero.flac", mapping)

    def test_track_bpm_sources_prefers_rekordbox_and_flags_large_mismatch(self) -> None:
        bpm_info = bs.track_bpm_sources(
            r"C:\Music\Track One.flac",
            {"bpm": 95.7},
            rekordbox_bpm=19200,
        )

        self.assertEqual(bpm_info.preferred_source, "rekordbox")
        self.assertEqual(bpm_info.preferred_bpm, 192.0)
        self.assertEqual(bpm_info.rbassist_bpm, 95.7)
        self.assertEqual(bpm_info.delta, -96.3)
        self.assertTrue(bpm_info.large_mismatch)
