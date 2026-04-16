import pathlib
import tempfile
import unittest

import numpy as np
import yaml

from rbassist import safe_tagstore, tag_model, tagstore, utils


class TagModelEffectiveTagsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = pathlib.Path(self.tmp.name)

        self.orig_meta = utils.META
        self.orig_tagstore_config_dir = tagstore._CONFIG_DIR
        self.orig_tagstore_file = tagstore._TAG_FILE
        self.orig_safe_config_dir = safe_tagstore._CONFIG_DIR
        self.orig_user_tags = safe_tagstore._USER_TAGS
        self.orig_ai_suggestions = safe_tagstore._AI_SUGGESTIONS
        self.orig_correction_log = safe_tagstore._CORRECTION_LOG

        config_dir = self.tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        utils.META = self.tmp_path / "meta.json"
        tagstore._CONFIG_DIR = config_dir
        tagstore._TAG_FILE = config_dir / "tags.yml"
        safe_tagstore._CONFIG_DIR = config_dir
        safe_tagstore._USER_TAGS = config_dir / "my_tags.yml"
        safe_tagstore._AI_SUGGESTIONS = config_dir / "ai_suggestions.json"
        safe_tagstore._CORRECTION_LOG = config_dir / "tag_corrections.json"

        self.track_a = str(self.tmp_path / "Artist - A.mp3")
        self.track_b = str(self.tmp_path / "Artist - B.mp3")
        emb_a = self.tmp_path / "a.npy"
        emb_b = self.tmp_path / "b.npy"
        np.save(emb_a, np.array([1.0, 0.0], dtype=np.float32))
        np.save(emb_b, np.array([0.9, 0.1], dtype=np.float32))

        utils.save_meta(
            {
                "tracks": {
                    self.track_a: {"embedding": str(emb_a)},
                    self.track_b: {"embedding": str(emb_b)},
                }
            }
        )

        safe_tagstore._USER_TAGS.write_text(
            yaml.safe_dump(
                {
                    "version": "1.0",
                    "tracks": {
                        self.track_a: ["Peak Hour"],
                    },
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        tagstore._TAG_FILE.write_text(
            yaml.safe_dump(
                {
                    "available": ["Peak Hour"],
                    "library": {
                        self.track_b: ["Peak Hour"],
                    },
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        utils.META = self.orig_meta
        tagstore._CONFIG_DIR = self.orig_tagstore_config_dir
        tagstore._TAG_FILE = self.orig_tagstore_file
        safe_tagstore._CONFIG_DIR = self.orig_safe_config_dir
        safe_tagstore._USER_TAGS = self.orig_user_tags
        safe_tagstore._AI_SUGGESTIONS = self.orig_ai_suggestions
        safe_tagstore._CORRECTION_LOG = self.orig_correction_log
        self.tmp.cleanup()

    def test_learn_tag_profiles_uses_effective_library_tags(self) -> None:
        meta = utils.load_meta()

        profiles = tag_model.learn_tag_profiles(min_samples=2, meta=meta)

        self.assertIn("Peak Hour", profiles)
        self.assertEqual(profiles["Peak Hour"].samples, 2)

        evaluated = tag_model.evaluate_existing_tags(
            [self.track_a, self.track_b],
            profiles,
            meta=meta,
        )

        self.assertEqual(evaluated[self.track_a][0][0], "Peak Hour")
        self.assertEqual(evaluated[self.track_b][0][0], "Peak Hour")


if __name__ == "__main__":
    unittest.main()
