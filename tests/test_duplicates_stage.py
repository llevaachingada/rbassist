import pathlib
import tempfile
import unittest

from rbassist import duplicates


class DuplicateStageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _meta(self, keep: pathlib.Path, lose: pathlib.Path) -> dict:
        return {
            "tracks": {
                str(keep): {"artist": "Artist", "title": "Song", "duration": 200},
                str(lose): {"artist": "Artist", "title": "Song", "duration": 200},
            }
        }

    def test_stage_duplicates_copy(self) -> None:
        keep = self.base / "keep.wav"
        lose = self.base / "dup.wav"
        keep.write_bytes(b"a")
        lose.write_bytes(b"b")
        stage_dir = self.base / "stage"

        staged = duplicates.stage_duplicates(self._meta(keep, lose), str(stage_dir), move=False, dry_run=False)
        self.assertEqual(len(staged), 1)
        self.assertTrue((stage_dir / "dup.wav").exists())
        self.assertTrue(lose.exists())  # copy leaves original

    def test_stage_duplicates_move(self) -> None:
        keep = self.base / "keep2.wav"
        lose = self.base / "dup2.wav"
        keep.write_bytes(b"a")
        lose.write_bytes(b"b")
        stage_dir = self.base / "stage2"

        duplicates.stage_duplicates(self._meta(keep, lose), str(stage_dir), move=True, dry_run=False)
        self.assertTrue((stage_dir / "dup2.wav").exists())
        self.assertFalse(lose.exists())  # move removes original


if __name__ == "__main__":
    unittest.main()
