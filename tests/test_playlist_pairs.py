from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from unittest import mock

from scripts import export_playlist_pairs
from rbassist import playlist_pairs as pp
from rbassist.playlist_expand import SeedPlaylist, SeedTrack


def _track(path: str, *, bpm: float = 128.0, key: str = "8A") -> SeedTrack:
    return SeedTrack(
        rekordbox_path=path,
        meta_path=path,
        bpm=bpm,
        key=key,
        embedding_path=f"{path}.npy",
        matched_by="test",
    )


def _playlist(name: str, tracks: list[SeedTrack]) -> SeedPlaylist:
    return SeedPlaylist(source="manual", seed_ref=name, playlist_name=name, tracks=tracks, diagnostics={})


class PlaylistPairDatasetTests(unittest.TestCase):
    def test_builds_adjacent_and_weak_positive_pairs_from_embedded_tracks(self) -> None:
        a, b, c = _track("a"), _track("b"), _track("c")
        playlist = _playlist("Warmup", [a, b, c])
        meta = {
            "a": {"embedding": "a.npy", "bpm": 128.0, "key": "8A"},
            "b": {"embedding": "b.npy", "bpm": 129.0, "key": "8A"},
            "c": {"embedding": "c.npy", "bpm": 130.0, "key": "8A"},
        }

        result = pp.build_playlist_pair_dataset(
            [playlist],
            meta_tracks=meta,
            negatives_per_positive=0,
            max_pairs_per_playlist=10,
        )

        pair_types = [row["pair_type"] for row in result.rows]
        self.assertEqual(pair_types.count("adjacent_positive"), 2)
        self.assertEqual(pair_types.count("same_playlist_weak_positive"), 1)
        self.assertEqual(result.rows[0]["left_path"], "a")
        self.assertEqual(result.rows[0]["right_path"], "b")
        self.assertEqual(result.rows[0]["label"], 1.0)
        self.assertEqual(result.diagnostics["positive_pairs"], 3)

    def test_skips_unmapped_or_unembedded_tracks(self) -> None:
        a = _track("a")
        missing = _track("missing")
        playlist = _playlist("Warmup", [a, missing])
        meta = {"a": {"embedding": "a.npy"}}

        result = pp.build_playlist_pair_dataset([playlist], meta_tracks=meta)

        self.assertEqual(result.rows, [])
        self.assertEqual(result.diagnostics["playlists_skipped"], 1)

    def test_negative_sampling_is_deterministic_and_labels_buckets(self) -> None:
        a, b = _track("a", bpm=128.0, key="8A"), _track("b", bpm=129.0, key="8A")
        c, d = _track("c", bpm=160.0, key="2A"), _track("d", bpm=161.0, key="2A")
        playlists = [_playlist("One", [a, b]), _playlist("Two", [c, d])]
        meta = {
            "a": {"embedding": "a.npy", "bpm": 128.0, "key": "8A"},
            "b": {"embedding": "b.npy", "bpm": 129.0, "key": "8A"},
            "c": {"embedding": "c.npy", "bpm": 160.0, "key": "2A"},
            "d": {"embedding": "d.npy", "bpm": 161.0, "key": "2A"},
        }

        result = pp.build_playlist_pair_dataset(
            playlists,
            meta_tracks=meta,
            include_weak_positives=False,
            negatives_per_positive=1,
            random_seed=7,
        )

        negatives = [row for row in result.rows if row["pair_type"] == "different_playlist_negative"]
        self.assertEqual(len(negatives), 2)
        self.assertTrue(all(row["left_path"] != row["right_path"] for row in negatives))
        self.assertTrue(all(row["label"] == 0.0 for row in negatives))

    def test_jsonl_writer_uses_rows_without_embedding_arrays(self) -> None:
        row = {
            "left_path": "a",
            "right_path": "b",
            "left_embedding": "a.npy",
            "right_embedding": "b.npy",
            "label": 1.0,
        }
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td) / "pairs.jsonl"
            pp.write_pair_dataset_jsonl([row], out)

            payload = json.loads(out.read_text(encoding="utf-8").strip())

        self.assertEqual(payload["left_embedding"], "a.npy")
        self.assertNotIn("left_vector", payload)
        self.assertNotIn("right_vector", payload)

    def test_loader_uses_rekordbox_playlist_ids_when_discovering_db_playlists(self) -> None:
        loaded = _playlist("Warmup", [_track("a"), _track("b")])
        with mock.patch.object(
            pp,
            "list_rekordbox_playlists",
            return_value=[
                {"source": "db", "name": "Smart", "path": "Folder/Smart", "id": 7, "is_smart_playlist": True},
                {"source": "db", "name": "radio 10/22", "path": "Folder/radio 10/22", "id": 42},
            ],
        ), mock.patch.object(pp, "load_rekordbox_playlist", return_value=loaded) as load_playlist:
            playlists = pp.load_playlists_for_dataset(source="db")

        self.assertEqual(playlists, [loaded])
        load_playlist.assert_called_once_with(42, source="db", playlist_path="Folder/radio 10/22", xml_path=None)

    def test_loader_skips_playlist_load_errors_by_default(self) -> None:
        loaded = _playlist("Warmup", [_track("a"), _track("b")])
        with mock.patch.object(
            pp,
            "list_rekordbox_playlists",
            return_value=[
                {"source": "db", "name": "Broken", "path": "Folder/Broken", "id": 1},
                {"source": "db", "name": "Warmup", "path": "Folder/Warmup", "id": 2},
            ],
        ), mock.patch.object(
            pp,
            "load_rekordbox_playlist",
            side_effect=[RuntimeError("smart playlist load failed"), loaded],
        ):
            playlists = pp.load_playlists_for_dataset(source="db")

        self.assertEqual(playlists, [loaded])

    def test_export_script_dry_run_does_not_write_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td) / "pairs.jsonl"
            summary = pathlib.Path(td) / "summary.json"
            result = pp.PairDatasetResult(
                rows=[{"left_path": "a", "right_path": "b", "label": 1.0}],
                diagnostics={"rows_total": 1},
            )
            with mock.patch.object(export_playlist_pairs, "load_playlists_for_dataset", return_value=[]), \
                    mock.patch.object(export_playlist_pairs, "load_meta", return_value={"tracks": {}}), \
                    mock.patch.object(export_playlist_pairs, "build_playlist_pair_dataset", return_value=result), \
                    mock.patch.object(export_playlist_pairs, "write_pair_dataset_jsonl") as writer:
                code = export_playlist_pairs.main(
                    ["--dry-run", "--out", str(out), "--summary", str(summary)]
                )

            self.assertEqual(code, 0)
            writer.assert_not_called()
            self.assertFalse(out.exists())
            self.assertTrue(summary.exists())


if __name__ == "__main__":
    unittest.main()
