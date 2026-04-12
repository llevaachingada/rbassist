from __future__ import annotations

import subprocess
import sys
import textwrap
import unittest


def _import_guard_script(module_name: str, blocked_prefixes: list[str]) -> str:
    return textwrap.dedent(
        f"""
        import importlib
        import sys

        blocked_prefixes = {blocked_prefixes!r}

        class Guard:
            def find_spec(self, fullname, path=None, target=None):
                for prefix in blocked_prefixes:
                    if fullname == prefix or fullname.startswith(prefix + "."):
                        raise ImportError(f"blocked import: {{fullname}}")
                return None

        sys.meta_path.insert(0, Guard())
        importlib.import_module({module_name!r})
        for prefix in blocked_prefixes:
            for loaded in list(sys.modules):
                if loaded == prefix or loaded.startswith(prefix + "."):
                    raise SystemExit(1)
        raise SystemExit(0)
        """
    )


def _assert_import_light(testcase: unittest.TestCase, module_name: str, blocked_prefixes: list[str]) -> None:
    result = subprocess.run(
        [sys.executable, "-c", _import_guard_script(module_name, blocked_prefixes)],
        capture_output=True,
        text=True,
        check=False,
    )
    testcase.assertEqual(
        result.returncode,
        0,
        msg=(
            f"Importing {module_name} should not load {blocked_prefixes}. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        ),
    )


class BridgeBoundaryTests(unittest.TestCase):
    def test_runtime_and_ui_services_do_not_import_gui_toolkits(self) -> None:
        for module_name in ["rbassist.runtime", "rbassist.ui_services"]:
            with self.subTest(module=module_name):
                _assert_import_light(
                    self,
                    module_name,
                    ["nicegui", "PySide6", "PySide6.QtCore", "PySide6.QtWidgets"],
                )

    def test_ui_jobs_remains_import_light(self) -> None:
        _assert_import_light(
            self,
            "rbassist.ui.jobs",
            [
                "nicegui",
                "rbassist.ui.app",
                "PySide6",
                "PySide6.QtCore",
                "PySide6.QtWidgets",
            ],
        )

    def test_desktop_app_remains_import_light(self) -> None:
        _assert_import_light(
            self,
            "rbassist.desktop.app",
            [
                "nicegui",
                "PySide6",
                "PySide6.QtCore",
                "PySide6.QtWidgets",
                "rbassist.utils",
            ],
        )


if __name__ == "__main__":
    unittest.main()
