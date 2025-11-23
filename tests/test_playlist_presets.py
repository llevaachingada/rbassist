import pathlib
import tempfile
import unittest

from rbassist import playlist_presets as presets


class PlaylistPresetsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.tmp.name)
        self.orig_dir = presets._CONFIG_DIR
        self.orig_file = presets._PRESET_FILE
        presets._CONFIG_DIR = base / "config"
        presets._PRESET_FILE = presets._CONFIG_DIR / "playlist_presets.yml"

    def tearDown(self) -> None:
        presets._CONFIG_DIR = self.orig_dir
        presets._PRESET_FILE = self.orig_file
        self.tmp.cleanup()

    def test_upsert_and_load(self) -> None:
        presets.upsert_preset(
            {
                "name": "Warmup",
                "output": "warmup.xml",
                "mytag": "Warm-up",
                "rating_min": 3,
                "since": "2024-01-01",
                "until": "",
            }
        )
        loaded = presets.load_presets()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["name"], "Warmup")

        presets.delete_preset("Warmup")
        self.assertEqual(presets.load_presets(), [])


if __name__ == "__main__":
    unittest.main()
