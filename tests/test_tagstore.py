import tempfile
import unittest
import pathlib

import yaml

from rbassist import tagstore, utils


class TagStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        tmp_path = pathlib.Path(self.tmp.name)
        self.orig_config_dir = tagstore._CONFIG_DIR
        self.orig_tag_file = tagstore._TAG_FILE
        self.orig_meta = utils.META

        tagstore._CONFIG_DIR = tmp_path / "config"
        tagstore._TAG_FILE = tagstore._CONFIG_DIR / "tags.yml"
        utils.META = tmp_path / "meta.json"
        utils.save_meta({"tracks": {"song.wav": {}}})

    def tearDown(self) -> None:
        tagstore._CONFIG_DIR = self.orig_config_dir
        tagstore._TAG_FILE = self.orig_tag_file
        utils.META = self.orig_meta
        self.tmp.cleanup()

    def test_set_track_tags_updates_meta_and_config(self) -> None:
        tagstore.set_track_tags("song.wav", ["Peak", "Vocals"])
        meta = utils.load_meta()
        self.assertEqual(meta["tracks"]["song.wav"]["mytags"], ["Peak", "Vocals"])

        cfg = yaml.safe_load(tagstore._TAG_FILE.read_text("utf-8"))
        self.assertIn("Peak", cfg["available"])
        self.assertEqual(cfg["library"]["song.wav"], ["Peak", "Vocals"])

        # Clearing tags removes them from meta and library
        tagstore.set_track_tags("song.wav", [])
        meta_after = utils.load_meta()
        self.assertNotIn("mytags", meta_after["tracks"]["song.wav"])
        cfg_after = yaml.safe_load(tagstore._TAG_FILE.read_text("utf-8"))
        self.assertNotIn("song.wav", cfg_after.get("library", {}))


if __name__ == "__main__":
    unittest.main()
