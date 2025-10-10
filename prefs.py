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


def save_prefs(data: dict) -> None:
    CFG.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def set_folder_mode(path: str, mode: str) -> None:
    prefs = load_prefs()
    items = prefs.get("folders", [])
    items = [r for r in items if pathlib.Path(r.get("path", "")) != pathlib.Path(path)]
    items.insert(0, {"path": str(path), "mode": mode})
    prefs["folders"] = items
    if "default_mode" not in prefs:
        prefs["default_mode"] = "baseline"
    save_prefs(prefs)
