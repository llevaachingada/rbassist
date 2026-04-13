import types
import unittest
import subprocess
import sys
from unittest import mock

from rbassist.ui import app as ui_app


class _FakeMount:
    def __init__(self) -> None:
        self.cleared = 0
        self.entered = 0

    def clear(self) -> None:
        self.cleared += 1

    def __enter__(self) -> "_FakeMount":
        self.entered += 1
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


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

    def test_lazy_page_loader_renders_each_tab_once(self) -> None:
        mount = mock.Mock()
        loader = ui_app._LazyPageLoader(mounts={"discover": mount}, loaded=set())
        with mock.patch.object(ui_app, "_render_page_into_mount") as render_mock:
            loader.ensure_loaded("discover")
            loader.ensure_loaded("discover")
        render_mock.assert_called_once()

    def test_activate_page_toggles_shell_status(self) -> None:
        loader = mock.Mock()
        status = mock.Mock()
        ui_app._activate_page(loader, "discover", status)
        loader.ensure_loaded.assert_called_once_with("discover")
        status.set_status.assert_any_call("Loading Discover...", busy=True)
        status.set_status.assert_any_call("Ready", busy=False)

    def test_render_page_into_mount_renders_fallback_on_import_failure(self) -> None:
        mount = _FakeMount()
        spec = ui_app.PageSpec("discover", "Discover", "explore", "discover")
        with mock.patch.object(ui_app, "_load_page_module", return_value=(None, "ImportError: boom")) as load_mock, mock.patch.object(
            ui_app, "_render_page_fallback"
        ) as fallback_mock:
            ui_app._render_page_into_mount(mount, spec)
        self.assertEqual(mount.cleared, 1)
        self.assertEqual(mount.entered, 1)
        load_mock.assert_called_once_with("discover")
        fallback_mock.assert_called_once_with(spec, "ImportError: boom")

    def test_lazy_page_loader_only_loads_once(self) -> None:
        mount = _FakeMount()
        loader = ui_app._LazyPageLoader(mounts={"discover": mount}, loaded=set())
        spec = ui_app.PageSpec("discover", "Discover", "explore", "discover")
        with mock.patch.object(ui_app, "_render_page_into_mount") as render_mock:
            render_mock.side_effect = lambda mount_arg, spec_arg: None
            loader.ensure_loaded("discover")
            loader.ensure_loaded("discover")
        render_mock.assert_called_once_with(mount, spec)
        self.assertIn("discover", loader.loaded)

    def test_library_page_imports_without_matplotlib(self) -> None:
        script = r"""
import importlib
import sys

class BlockMatplotlib:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "matplotlib" or fullname.startswith("matplotlib."):
            raise ModuleNotFoundError("blocked matplotlib")
        return None

sys.meta_path.insert(0, BlockMatplotlib())
importlib.import_module("rbassist.ui.pages.library")
"""
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
