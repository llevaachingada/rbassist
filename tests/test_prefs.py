import tempfile
import pathlib
import unittest

import rbassist.prefs as prefs


class PrefsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.orig_cfg = prefs.CFG
        prefs.CFG = pathlib.Path(self.tmp.name) / "config.yml"
        if prefs.CFG.exists():
            prefs.CFG.unlink()

    def tearDown(self):
        prefs.CFG = self.orig_cfg

    def test_default_mode_when_config_missing(self):
        self.assertEqual(prefs.mode_for_path(str(pathlib.Path(self.tmp.name) / "song.mp3")), "baseline")

    def test_set_folder_mode_normalizes_and_first_match(self):
        base = pathlib.Path(self.tmp.name) / "music"
        nested = base / "vocals"
        base.mkdir()
        nested.mkdir()

        prefs.set_folder_mode(str(base), "baseline")
        prefs.set_folder_mode(str(nested), "stems")
        # repeat with different casing to ensure normalization replaces prior base entry
        prefs.set_folder_mode(str(base).upper(), "stems")

        data = prefs.load_prefs()
        self.assertEqual(len(data.get("folders", [])), 2)
        # newest entry should be the re-added base path
        self.assertEqual(data["folders"][0]["mode"], "stems")
        self.assertEqual(prefs.mode_for_path(str(nested / "track.wav")), "stems")
        self.assertEqual(prefs.mode_for_path(str(base / "other.wav")), "stems")
        # unrelated path falls back to default
        elsewhere = pathlib.Path(self.tmp.name) / "other" / "cut.wav"
        self.assertEqual(prefs.mode_for_path(str(elsewhere)), "baseline")


if __name__ == "__main__":
    unittest.main()
