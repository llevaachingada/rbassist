from __future__ import annotations
import pathlib, yaml

CFG = (pathlib.Path(__file__).resolve().parents[1] / "rbassist" / "config.yml")
DEFAULT = {"folders": [], "default_mode": "baseline"}


def load_prefs() -> dict:
    if CFG.exists():
        try:
            return yaml.safe_load(CFG.read_text("utf-8")) or DEFAULT
        except Exception:
            return DEFAULT
    return DEFAULT


def mode_for_path(path: str) -> str:
    p = pathlib.Path(path).resolve()
    prefs = load_prefs()
    for rule in prefs.get("folders", []):
        r = pathlib.Path(rule.get("path", ""))
        try:
            if p.as_posix().startswith(r.resolve().as_posix()):
                return rule.get("mode", "baseline")
        except Exception:
            pass
    return prefs.get("default_mode", "baseline")

