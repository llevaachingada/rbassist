import pathlib
import tempfile
import unittest

from rbassist.utils import read_paths_file


class PathsFileTests(unittest.TestCase):
    def test_read_paths_file_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            (base / "crate").mkdir()
            abs_item = base / "absolute.wav"
            paths_file = base / "paths.txt"
            paths_file.write_text(
                "\n".join(
                    [
                        "# comment",
                        "",
                        "crate",
                        "\"crate\"",
                        str(abs_item),
                    ]
                ),
                encoding="utf-8",
            )

            out = read_paths_file(paths_file)
            self.assertEqual(out[0], str((base / "crate").resolve()))
            self.assertEqual(out[1], str((base / "crate").resolve()))
            self.assertEqual(out[2], str(abs_item))


if __name__ == "__main__":
    unittest.main()
