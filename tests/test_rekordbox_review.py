from __future__ import annotations

from rbassist.rekordbox_review import build_review_queues


def test_build_review_queues_extracts_high_conf_and_diff_type_groups() -> None:
    report = {
        "relink_suggestion_report": {
            "suggestions": [
                {
                    "classification": "high_confidence_unique",
                    "id": "1",
                    "source_path": "old.mp3",
                    "title": "Track",
                    "artist": "Artist",
                    "row_length": 200.0,
                    "best_candidate": {
                        "path": "new.flac",
                        "duration": 200.1,
                        "size": 123,
                        "score": 222.0,
                        "reasons": ["exact_basename"],
                    },
                },
                {
                    "classification": "ambiguous",
                    "id": "2",
                    "source_path": "amb.mp3",
                    "candidates": [{"path": "a.mp3"}, {"path": "b.mp3"}],
                },
            ]
        },
        "duplicate_dry_run_report": {
            "groups": [
                {
                    "stem_key": "artist track",
                    "keep": {"path": "keep.flac", "extension": ".flac"},
                    "extensions": [".flac", ".mp3"],
                    "duration_span": [200.0, 200.5],
                    "candidates": [{"path": "keep.flac"}, {"path": "drop.mp3"}],
                },
                {
                    "stem_key": "other",
                    "keep": {"path": "keep2.flac", "extension": ".flac"},
                    "extensions": [".flac"],
                    "duration_span": [100.0, 100.0],
                    "candidates": [{"path": "keep2.flac"}, {"path": "copy.flac"}],
                },
            ]
        },
    }
    queues = build_review_queues(report)
    assert queues["counts"]["high_confidence_relinks_total"] == 1
    assert queues["counts"]["ambiguous_relinks_total"] == 1
    assert queues["counts"]["same_name_different_type_groups_total"] == 1
    assert queues["high_confidence_relinks"][0]["target_path"] == "new.flac"
    assert queues["same_name_different_type_duplicates"][0]["keep_path"] == "keep.flac"
