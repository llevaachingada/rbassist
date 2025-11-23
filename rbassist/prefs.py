from __future__ import annotations
import pathlib, yaml

CFG = (pathlib.Path(__file__).resolve().parents[1] / "rbassist" / "config.yml")
DEFAULT = {"folders": [], "default_mode": "baseline"}


def _normalized(path: str) -> str:
    try:
        resolved = pathlib.Path(path).expanduser().resolve(strict=False)
    except Exception:
        resolved = pathlib.Path(path).expanduser()
    return resolved.as_posix().casefold()


def load_prefs() -> dict:
    if CFG.exists():
        try:
            return yaml.safe_load(CFG.read_text("utf-8")) or DEFAULT
        except Exception:
            return DEFAULT
    return DEFAULT


def mode_for_path(path: str) -> str:
    prefs = load_prefs()
    target = _normalized(path)
    for rule in prefs.get("folders", []):
        raw = rule.get("path", "")
        if not raw:
            continue
        if target.startswith(_normalized(raw)):
            return rule.get("mode", "baseline")
    return prefs.get("default_mode", "baseline")


def save_prefs(data: dict) -> None:
    CFG.parent.mkdir(parents=True, exist_ok=True)
    CFG.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def set_folder_mode(path: str, mode: str) -> None:
    prefs = load_prefs()
    items = prefs.get("folders", [])
    incoming_norm = _normalized(path)
    clean_items = []
    for row in items:
        existing = row.get("path", "")
        if existing and _normalized(existing) == incoming_norm:
            continue
        clean_items.append(row)
    clean_items.insert(0, {"path": str(pathlib.Path(path).expanduser()), "mode": mode})
    prefs["folders"] = clean_items
    if "default_mode" not in prefs:
        prefs["default_mode"] = "baseline"
    save_prefs(prefs)
