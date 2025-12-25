#!/usr/bin/env python3
"""Quick validation for the AI tagging modules.

This is intentionally a script (not a pytest module) so it does not affect
`pytest` runs or CI discovery.
"""

from __future__ import annotations

import sys
from importlib import import_module


def _check_import(module_path: str) -> tuple[bool, str]:
    try:
        import_module(module_path)
        return True, ""
    except Exception as exc:
        return False, f"{exc.__class__.__name__}: {exc}"


def main() -> int:
    modules = [
        "rbassist.safe_tagstore",
        "rbassist.active_learning",
        "rbassist.user_model",
        "rbassist.tag_model",
        "rbassist.ui.pages.ai_tagging",
    ]

    ok = True
    print("AI tagging validation")
    print("-" * 60)

    for mod in modules:
        passed, msg = _check_import(mod)
        if passed:
            print(f"[OK]   {mod}")
        else:
            ok = False
            print(f"[FAIL] {mod} ({msg})")

    if ok:
        try:
            page = import_module("rbassist.ui.pages.ai_tagging")
            has_render = hasattr(page, "render")
            print(f"[OK]   ai_tagging.render exists: {has_render}")
            ok = ok and has_render
        except Exception as exc:
            ok = False
            print(f"[FAIL] ai_tagging.render check ({exc.__class__.__name__}: {exc})")

    print("-" * 60)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

