from __future__ import annotations

import xml.etree.ElementTree as ET

import numpy as np

from rbassist.cue_templates import load_cue_template
from rbassist.analyze import _store_generated_cues
from rbassist.cue_templates import CueTemplate
from rbassist.cues import CueAnchors, propose_cues
from rbassist.export_xml import write_rekordbox_xml


def test_propose_cues_uses_rekordbox_aligned_types_and_slots(monkeypatch) -> None:
    template = CueTemplate.from_mapping({})
    anchors = CueAnchors(
        duration_s=240.0,
        beat_s=0.46875,
        first_downbeat=8.0,
        first_drop=72.0,
        second_drop=None,
        break_start=56.0,
        hot_b_start=40.0,
        mix_out_start=176.0,
        end_guard_start=208.0,
    )
    monkeypatch.setattr("rbassist.cues.estimate_cue_anchors", lambda *args, **kwargs: anchors)

    cues = propose_cues(np.zeros(1024, dtype=np.float32), 512, 128.0, template=template)

    assert any(c["name"] == "Memory 1" and c["type"] == 0 and c["num"] == -1 for c in cues)
    assert any(c["name"] == "Hot A" and c["type"] == 4 and c["num"] == 0 for c in cues)
    assert any(c["name"] == "Hot D" and c["type"] == 0 and c["num"] == 3 for c in cues)
    assert any(c["name"] == "Drop Memory" and c["type"] == 0 and c["num"] == -1 for c in cues)


def test_propose_cues_honors_template_overrides_and_role_toggles(monkeypatch) -> None:
    template = CueTemplate.from_mapping(
        {
            "roles": {
                "memory_1": {"enabled": False},
                "hot_a": {"name": "Intro Loop", "slot": 7, "bars": 8},
                "drop_memory": {"name": "Main Drop"},
                "mix_out_f": {"enabled": False},
            }
        }
    )
    anchors = CueAnchors(
        duration_s=180.0,
        beat_s=0.4615,
        first_downbeat=4.0,
        first_drop=68.0,
        second_drop=None,
        break_start=52.0,
        hot_b_start=36.0,
        mix_out_start=132.0,
        end_guard_start=164.0,
    )
    monkeypatch.setattr("rbassist.cues.estimate_cue_anchors", lambda *args, **kwargs: anchors)

    cues = propose_cues(np.zeros(1024, dtype=np.float32), 512, 130.0, template=template)

    assert not any(c["name"] == "Memory 1" for c in cues)
    assert any(c["name"] == "Intro Loop" and c["type"] == 4 and c["num"] == 7 for c in cues)
    assert any(c["name"] == "Main Drop" and c["type"] == 0 and c["num"] == -1 for c in cues)
    assert not any(c["name"] == "Hot F" for c in cues)


def test_store_generated_cues_preserves_existing_cues_by_default() -> None:
    info = {"cues": [{"name": "Existing", "type": 0, "num": -1, "start": 10.0, "end": 10.0}]}
    replacement = [{"name": "New", "type": 4, "num": 0, "start": 20.0, "end": 35.0}]

    changed = _store_generated_cues(info, replacement, overwrite_cues=False)
    assert changed is False
    assert info["cues"][0]["name"] == "Existing"

    changed = _store_generated_cues(info, replacement, overwrite_cues=True)
    assert changed is True
    assert info["cues"][0]["name"] == "New"


def test_export_xml_preserves_generated_type_and_slot_fields(monkeypatch, tmp_path) -> None:
    template = CueTemplate.from_mapping({})
    anchors = CueAnchors(
        duration_s=240.0,
        beat_s=0.46875,
        first_downbeat=8.0,
        first_drop=72.0,
        second_drop=None,
        break_start=56.0,
        hot_b_start=40.0,
        mix_out_start=176.0,
        end_guard_start=208.0,
    )
    monkeypatch.setattr("rbassist.cues.estimate_cue_anchors", lambda *args, **kwargs: anchors)
    cues = propose_cues(np.zeros(1024, dtype=np.float32), 512, 128.0, template=template)

    meta = {
        "tracks": {
            str(tmp_path / "Artist - Track.mp3"): {
                "artist": "Artist",
                "title": "Track",
                "bpm": 128.0,
                "mytags": ["Peak Hour"],
                "cues": cues,
            }
        }
    }

    out_path = tmp_path / "rbassist.xml"
    write_rekordbox_xml(meta, str(out_path), playlist_name="Test")

    root = ET.parse(out_path).getroot()
    marks = root.findall(".//POSITION_MARK")
    assert any(mark.get("Name") == "Hot A" and mark.get("Type") == "4" and mark.get("Num") == "0" for mark in marks)
    assert any(mark.get("Name") == "Hot D" and mark.get("Type") == "0" and mark.get("Num") == "3" for mark in marks)
    assert any(mark.get("Name") == "Drop Memory" and mark.get("Type") == "0" and mark.get("Num") == "-1" for mark in marks)


def test_load_cue_template_applies_profile_role_overrides(monkeypatch, tmp_path) -> None:
    profile_path = tmp_path / "cue_templates.yml"
    profile_path.write_text(
        """
cue_template_profile: custom
profiles:
  custom:
    roles:
      memory_1:
        enabled: false
      hot_a:
        name: Intro Loop
        slot: 7
        bars: 8
        """.strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr("rbassist.cue_templates._PROFILE_FILE", profile_path)
    monkeypatch.setattr("rbassist.cue_templates._ENTRY_FILE", tmp_path / "missing.yml")

    template = load_cue_template()

    assert template.profile_name == "custom"
    assert template.entry_for("memory_1") is None
    hot_a = template.entry_for("hot_a")
    assert hot_a is not None
    assert hot_a.name == "Intro Loop"
    assert hot_a.slot == 7
    assert hot_a.bars == 8
