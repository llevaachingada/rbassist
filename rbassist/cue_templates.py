from __future__ import annotations

from dataclasses import dataclass, field
import pathlib
from typing import Any

import yaml


_CONFIG_DIR = pathlib.Path(__file__).resolve().parents[1] / "config"
_ENTRY_FILE = _CONFIG_DIR / "cue_template.yml"
_PROFILE_FILE = _CONFIG_DIR / "cue_templates.yml"


@dataclass(frozen=True)
class CueTemplateEntry:
    cue_id: str
    name: str
    kind: str
    anchor: str
    bars: int | None = None
    slot: int | None = None
    enabled: bool = True


@dataclass(frozen=True)
class CueTemplate:
    profile_name: str = "default"
    hot_a_bars: int = 16
    hot_b_bars: int = 16
    hot_c_bars: int = 16
    hot_e_bars: int = 16
    hot_f_bars: int = 16
    mix_in_gap_bars: int = 32
    second_drop_bars_after_first: int = 32
    mix_out_lead_bars: int = 48
    end_guard_lead_bars: int = 16
    include_second_drop_memory: bool = False
    include_end_memory: bool = True
    slots: dict[str, int] = field(default_factory=dict)
    entries: tuple[CueTemplateEntry, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(
        cls,
        mapping: dict[str, Any],
        profile_name: str = "default",
    ) -> CueTemplate:
        roles = mapping.get("roles", {}) if isinstance(mapping, dict) else {}
        if not isinstance(roles, dict):
            roles = {}

        entries = _merge_entries(roles)
        slots = {
            entry.cue_id: entry.slot
            for entry in entries
            if entry.slot is not None
        }

        return cls(
            profile_name=profile_name,
            hot_a_bars=max(1, int(_role_value(roles, "hot_a", "bars", mapping.get("hot_a_bars", 16)) or 16)),
            hot_b_bars=max(1, int(_role_value(roles, "hot_b", "bars", mapping.get("hot_b_bars", 16)) or 16)),
            hot_c_bars=max(1, int(_role_value(roles, "hot_c", "bars", mapping.get("hot_c_bars", 16)) or 16)),
            hot_e_bars=max(
                1,
                int(_role_value(roles, "mix_out_e", "bars", mapping.get("hot_e_bars", 16)) or 16),
            ),
            hot_f_bars=max(
                1,
                int(_role_value(roles, "mix_out_f", "bars", mapping.get("hot_f_bars", 16)) or 16),
            ),
            mix_in_gap_bars=max(
                1,
                int(
                    _role_value(
                        roles,
                        "hot_b",
                        "after_downbeat_bars",
                        mapping.get("mix_in_gap_bars", 32),
                    )
                    or 32
                ),
            ),
            second_drop_bars_after_first=max(
                1,
                int(
                    _role_value(
                        roles,
                        "second_drop_memory",
                        "after_drop_bars",
                        mapping.get("second_drop_bars_after_first", 32),
                    )
                    or 32
                ),
            ),
            mix_out_lead_bars=max(
                1,
                int(
                    _role_value(
                        roles,
                        "mix_out_e",
                        "before_end_bars",
                        mapping.get("mix_out_lead_bars", 48),
                    )
                    or 48
                ),
            ),
            end_guard_lead_bars=max(
                1,
                int(
                    _role_value(
                        roles,
                        "mix_out_f",
                        "before_end_bars",
                        mapping.get("end_guard_lead_bars", 16),
                    )
                    or 16
                ),
            ),
            include_second_drop_memory=bool(
                _role_value(
                    roles,
                    "second_drop_memory",
                    "enabled",
                    mapping.get("include_second_drop_memory", False),
                )
            ),
            include_end_memory=bool(
                _role_value(
                    roles,
                    "end_memory",
                    "enabled",
                    mapping.get("include_end_memory", True),
                )
            ),
            slots=slots,
            entries=entries,
        )

    def entry_for(self, cue_id: str) -> CueTemplateEntry | None:
        for entry in self.entries:
            if entry.cue_id == cue_id:
                return entry
        return None

    def slot_for(self, cue_id: str, default: int) -> int:
        slot = self.slots.get(cue_id)
        if slot is None:
            entry = self.entry_for(cue_id)
            slot = entry.slot if entry is not None else default
        try:
            slot = int(slot)
        except Exception:
            return default
        if slot < 0 or slot > 7:
            return default
        return slot

    def bars_for(self, cue_id: str, default: int) -> int:
        entry = self.entry_for(cue_id)
        if entry is not None and entry.bars is not None:
            try:
                return max(1, int(entry.bars))
            except Exception:
                return default

        mapping = {
            "hot_a": self.hot_a_bars,
            "hot_b": self.hot_b_bars,
            "hot_c": self.hot_c_bars,
            "mix_out_e": self.hot_e_bars,
            "mix_out_f": self.hot_f_bars,
        }
        value = mapping.get(cue_id, default)
        try:
            return max(1, int(value))
        except Exception:
            return default


def _default_entries() -> tuple[CueTemplateEntry, ...]:
    return (
        CueTemplateEntry("memory_1", "Memory 1", "memory_point", "first_downbeat"),
        CueTemplateEntry("hot_a", "Hot A", "hot_loop", "first_downbeat", bars=16, slot=0),
        CueTemplateEntry("hot_b", "Hot B", "hot_loop", "later_mix_in", bars=16, slot=1),
        CueTemplateEntry("hot_c", "Hot C", "hot_loop", "break_start", bars=16, slot=2),
        CueTemplateEntry("hot_d", "Hot D", "hot_point", "first_drop", slot=3),
        CueTemplateEntry("drop_memory", "Drop Memory", "memory_point", "first_drop"),
        CueTemplateEntry(
            "second_drop_memory",
            "Second Drop",
            "memory_point",
            "second_drop",
            enabled=False,
        ),
        CueTemplateEntry("mix_out_e", "Hot E", "hot_loop", "mix_out", bars=16, slot=4),
        CueTemplateEntry("mix_out_f", "Hot F", "hot_loop", "end_guard", bars=16, slot=5),
        CueTemplateEntry("end_memory", "End Memory", "memory_point", "end_guard"),
    )


def _default_role_mapping() -> dict[str, dict[str, Any]]:
    roles: dict[str, dict[str, Any]] = {}
    for entry in _default_entries():
        roles[entry.cue_id] = {
            "name": entry.name,
            "kind": entry.kind,
            "anchor": entry.anchor,
            "bars": entry.bars,
            "slot": entry.slot,
            "enabled": entry.enabled,
        }
    return roles


def _safe_load_yaml(path: pathlib.Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _coerce_entry(raw: dict[str, Any]) -> CueTemplateEntry | None:
    cue_id = str(raw.get("cue_id", "")).strip()
    name = str(raw.get("name", "")).strip()
    kind = str(raw.get("kind", "")).strip()
    anchor = str(raw.get("anchor", "")).strip()
    if not cue_id or not name or not kind or not anchor:
        return None

    bars = raw.get("bars")
    if bars is not None:
        try:
            bars = max(1, int(bars))
        except Exception:
            bars = None

    slot = raw.get("slot")
    if slot is not None:
        try:
            slot = int(slot)
        except Exception:
            slot = None
        if slot is not None and (slot < 0 or slot > 7):
            slot = None

    return CueTemplateEntry(
        cue_id=cue_id,
        name=name,
        kind=kind,
        anchor=anchor,
        bars=bars,
        slot=slot,
        enabled=bool(raw.get("enabled", True)),
    )


def _merge_entries(roles: dict[str, Any]) -> tuple[CueTemplateEntry, ...]:
    default_roles = _default_role_mapping()
    entries: list[CueTemplateEntry] = []
    seen: set[str] = set()

    for cue_id, raw in default_roles.items():
        override = roles.get(cue_id, {})
        merged = dict(raw)
        if isinstance(override, dict):
            merged.update(override)
        entry = _coerce_entry({"cue_id": cue_id, **merged})
        if entry is not None and entry.enabled:
            entries.append(entry)
        seen.add(cue_id)

    for cue_id, raw in roles.items():
        if cue_id in seen or not isinstance(raw, dict):
            continue
        entry = _coerce_entry({"cue_id": cue_id, **raw})
        if entry is not None and entry.enabled:
            entries.append(entry)

    return tuple(entries)


def _load_entry_mapping() -> dict[str, Any]:
    if not _ENTRY_FILE.exists():
        return {"roles": _default_role_mapping()}

    data = _safe_load_yaml(_ENTRY_FILE)
    roles = data.get("roles", {})
    if isinstance(roles, dict):
        return {"roles": roles}

    rows = data.get("cues", [])
    if not isinstance(rows, list):
        return {"roles": _default_role_mapping()}

    loaded_roles: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        cue_id = str(raw.get("cue_id", "")).strip()
        if not cue_id:
            continue
        loaded_roles[cue_id] = dict(raw)

    return {"roles": loaded_roles} if loaded_roles else {"roles": _default_role_mapping()}


def _merge_template_mapping(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    base_roles = merged.get("roles", {})
    merged_roles = dict(base_roles) if isinstance(base_roles, dict) else {}

    override_roles = override.get("roles", {})
    if isinstance(override_roles, dict):
        for cue_id, raw in override_roles.items():
            if not isinstance(raw, dict):
                continue
            role = dict(merged_roles.get(cue_id, {}))
            role.update(raw)
            merged_roles[cue_id] = role

    if merged_roles:
        merged["roles"] = merged_roles

    for key, value in override.items():
        if key == "roles":
            continue
        merged[key] = value
    return merged


def load_cue_template(profile_name: str | None = None) -> CueTemplate:
    profile_data: dict[str, Any] = {}
    selected_name = profile_name or "default"

    if _PROFILE_FILE.exists():
        data = _safe_load_yaml(_PROFILE_FILE)
        profiles = data.get("profiles", {})
        if isinstance(profiles, dict) and profiles:
            default_name = str(
                data.get("cue_template_profile", "") or data.get("active_profile", "")
            ).strip() or selected_name
            selected_name = profile_name or default_name
            candidate = profiles.get(selected_name)
            if isinstance(candidate, dict):
                profile_data = candidate

    merged_mapping = _merge_template_mapping(_load_entry_mapping(), profile_data)
    return CueTemplate.from_mapping(merged_mapping, profile_name=selected_name)


def _role_value(roles: dict[str, Any], cue_id: str, field: str, default: Any) -> Any:
    raw = roles.get(cue_id, {})
    if not isinstance(raw, dict):
        return default
    return raw.get(field, default)
