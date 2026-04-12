"""rbassist NiceGUI-based desktop interface."""

from __future__ import annotations

__all__ = ["run", "main"]


def __getattr__(name: str):
    if name in __all__:
        from .app import main, run

        return {"run": run, "main": main}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
