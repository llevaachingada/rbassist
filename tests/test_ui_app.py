import types
import unittest
from unittest import mock

from rbassist.ui import app as ui_app


class UiAppTests(unittest.TestCase):
    def test_load_page_module_returns_module_on_success(self) -> None:
        fake_module = types.SimpleNamespace(render=lambda: None)
        with mock.patch.object(ui_app, "import_module", return_value=fake_module):
            module, error = ui_app._load_page_module("discover")
        self.assertIs(module, fake_module)
        self.assertIsNone(error)

    def test_load_page_module_returns_error_on_failure(self) -> None:
        with mock.patch.object(ui_app, "import_module", side_effect=ImportError("boom")):
            module, error = ui_app._load_page_module("discover")
        self.assertIsNone(module)
        self.assertEqual(error, "ImportError: boom")


if __name__ == "__main__":
    unittest.main()
