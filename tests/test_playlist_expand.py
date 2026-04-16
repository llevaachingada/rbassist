from __future__ import annotations

import json
import pathlib
import tempfile
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest import TestCase, mock

import numpy as np
from typer.testing import CliRunner

from rbassist import cli
from rbassist import playlist_expand as pe


class _Query:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _FakeDb:
    def __init__(self, playlists, rows):
        self.playlists = list(playlists)
        self.rows = list(rows)
        self.closed = False

    def get_playlist(self, **kwargs):
        matches = self.playlists
        for key, value in kwargs.items():
            matches = [pl for pl in matches if getattr(pl, key, None) == value]
        return _Query(matches)

    def get_playlist_contents(self, playlist):
        return _Query(self.rows)

    def close(self):
        self.closed = True


class _FakeXmlTrack:
    def __init__(self, location):
        self._location = location

    def get(self, key, default=None):
        if key == "Location":
            return self._location
        return default


class _FakeXmlNode:
    def __init__(self, name, keys=None, children=None):
        self.Name = name
        self.name = name
        self._keys = list(keys or [])
        self._children = list(children or [])
        self.is_folder = bool(self._children)

    def get_tracks(self):
        return list(self._keys)

    def get_playlists(self):
        return list(self._children)


class _FakeXml:
    def __init__(self, path):
        self.path = path
        chill = _FakeXmlNode("Chill", [1, 2])
        folder = _FakeXmlNode("Folder", children=[chill])
        self.root = _FakeXmlNode("ROOT", children=[folder])
        self.tracks = {
            1: _FakeXmlTrack("file://localhost/C:/Music/Chill/Seed One.flac"),
            2: _FakeXmlTrack("file://localhost/C:/Music/Chill/Seed Two.flac"),
        }

    def get_playlist(self, *names):
        node = self.root
        if not names:
            return node
        for name in names:
            for child in node.get_playlists():
                if child.name == name:
                    node = child
                    break
            else:
                raise KeyError(name)
        return node

    def get_track(self, TrackID=None, Location=None):
        if TrackID is not None:
            return self.tracks[TrackID]
        raise AssertionError("XML fake only supports TrackID lookup in this test")


class PlaylistExpandTests(TestCase):
    def test_resolve_controls_keeps_tight_preset_when_section_scores_are_enabled(self) -> None:
        controls = pe._resolve_playlist_expansion_controls(
            mode="tight",
            controls={"use_section_scores": True},
        )

        raw_weights = {
            "ann_centroid": 0.26,
            "ann_seed_coverage": 0.20,
            "group_match": 0.18,
            "bpm_match": 0.18,
            "key_match": 0.12,
            "tag_match": 0.06,
            "transition_outro_to_intro": 0.18,
        }
        total = sum(raw_weights.values())

        self.assertEqual(controls.mode, "tight")
        self.assertTrue(controls.use_section_scores)
        self.assertEqual(controls.filters.key_mode, "filter")
        for key, raw_value in raw_weights.items():
            self.assertAlmostEqual(getattr(controls.weights, key), raw_value / total)

    def test_seed_track_from_meta_prefers_rekordbox_bpm_without_losing_rbassist_bpm(self) -> None:
        meta_tracks = {
            r"C:\Music\Sets\Track A.flac": {
                "title": "Track A",
                "artist": "Artist A",
                "bpm": 123.05,
                "embedding": "track-a.npy",
            }
        }

        track = pe._seed_track_from_meta(
            r"C:\Music\Sets\Track A.flac",
            r"C:\Music\Sets\Track A.flac",
            meta_tracks,
            matched_by="path",
            fallback_bpm=124.0,
        )

        self.assertEqual(track.bpm, 124.0)
        self.assertEqual(track.rekordbox_bpm, 124.0)
        self.assertEqual(track.rbassist_bpm, 123.05)
        self.assertEqual(track.bpm_source, "rekordbox")
        self.assertFalse(track.bpm_mismatch)

    def test_list_rekordbox_playlists_db_returns_full_paths(self) -> None:
        playlists = [
            SimpleNamespace(Name="Folder", ID=1, ParentID=None, is_folder=True, is_smart_playlist=False),
            SimpleNamespace(Name="Warmup", ID=7, ParentID=1, is_folder=False, is_smart_playlist=False),
        ]

        with mock.patch.object(pe, "Rekordbox6Database", lambda: _FakeDb(playlists, [])):
            items = pe.list_rekordbox_playlists(source="db")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "Warmup")
        self.assertEqual(items[0]["path"], "Folder/Warmup")
        self.assertFalse(items[0]["is_folder"])

    def test_list_rekordbox_playlists_xml_returns_nested_paths(self) -> None:
        with mock.patch.object(pe, "RekordboxXml", _FakeXml):
            items = pe.list_rekordbox_playlists(source="xml", xml_path=r"C:\tmp\rekordbox.xml")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "Chill")
        self.assertEqual(items[0]["path"], "Folder/Chill")
        self.assertFalse(items[0]["is_folder"])

    def test_load_rekordbox_playlist_db_maps_aliases_and_reports_unresolved(self) -> None:
        playlists = [SimpleNamespace(Name="Warmup", ID=7, is_folder=False, is_smart_playlist=False)]
        rows = [
            SimpleNamespace(FolderPath="c:/music/sets/track a.flac", Title="Track A", ArtistName="Artist A"),
            SimpleNamespace(FolderPath="D:/Elsewhere/missing.mp3", Title="Track B", ArtistName="Artist B"),
        ]
        meta = {
            "tracks": {
                r"C:\Music\Sets\Track A.flac": {"title": "Track A", "artist": "Artist A"},
            }
        }

        with mock.patch.object(pe, "Rekordbox6Database", lambda: _FakeDb(playlists, rows)), mock.patch.object(
            pe, "load_meta", return_value=meta
        ):
            playlist = pe.load_rekordbox_playlist("Warmup", source="db")

        self.assertEqual(playlist.playlist_name, "Warmup")
        self.assertEqual(len(playlist.tracks), 2)
        self.assertEqual(playlist.tracks[0].meta_path, r"C:\Music\Sets\Track A.flac")
        self.assertIsNone(playlist.tracks[1].meta_path)
        self.assertEqual(playlist.diagnostics["matched_total"], 0)
        self.assertEqual(playlist.diagnostics["missing_embedding_total"], 1)
        self.assertEqual(playlist.diagnostics["unmapped_total"], 1)

    def test_load_rekordbox_playlist_db_rejects_ambiguous_name(self) -> None:
        playlists = [
            SimpleNamespace(Name="Warmup", ID=7, is_folder=False, is_smart_playlist=False),
            SimpleNamespace(Name="Warmup", ID=8, is_folder=False, is_smart_playlist=False),
        ]
        with mock.patch.object(pe, "Rekordbox6Database", lambda: _FakeDb(playlists, [])), mock.patch.object(
            pe, "load_meta", return_value={"tracks": {}}
        ):
            with self.assertRaises(ValueError):
                pe.load_rekordbox_playlist("Warmup", source="db")

    def test_load_rekordbox_playlist_db_uses_id_for_names_with_slashes(self) -> None:
        playlists = [
            SimpleNamespace(Name="DOWNLOAD CHUNX", ID=1, ParentID=None, is_folder=True, is_smart_playlist=False),
            SimpleNamespace(Name="radio 10/22", ID=42, ParentID=1, is_folder=False, is_smart_playlist=False),
        ]
        rows = [
            SimpleNamespace(FolderPath="c:/music/sets/track a.flac", Title="Track A", ArtistName="Artist A"),
        ]
        meta = {
            "tracks": {
                r"C:\Music\Sets\Track A.flac": {"title": "Track A", "artist": "Artist A", "embedding": "track-a.npy"},
            }
        }

        with mock.patch.object(pe, "Rekordbox6Database", lambda: _FakeDb(playlists, rows)), mock.patch.object(
            pe, "load_meta", return_value=meta
        ):
            playlist = pe.load_rekordbox_playlist(42, source="db")

        self.assertEqual(playlist.playlist_name, "radio 10/22")
        self.assertEqual(playlist.tracks[0].meta_path, r"C:\Music\Sets\Track A.flac")
        self.assertEqual(playlist.diagnostics["matched_total"], 1)

    def test_load_rekordbox_playlist_xml_reads_nested_playlist_by_leaf_name(self) -> None:
        meta = {
            "tracks": {
                r"C:\Music\Chill\Seed One.flac": {"title": "Seed One", "artist": "Artist", "embedding": "one.npy"},
                r"C:\Music\Chill\Seed Two.flac": {"title": "Seed Two", "artist": "Artist", "embedding": "two.npy"},
            }
        }

        with mock.patch.object(pe, "RekordboxXml", _FakeXml), mock.patch.object(pe, "load_meta", return_value=meta):
            playlist = pe.load_rekordbox_playlist("Chill", source="xml", xml_path=r"C:\tmp\rekordbox.xml")

        self.assertEqual(playlist.playlist_name, "Chill")
        self.assertEqual([track.meta_path for track in playlist.tracks], list(meta["tracks"].keys()))
        self.assertEqual(playlist.diagnostics["matched_total"], 2)

    def test_expand_playlist_preserves_seeds_and_applies_diversity_rerank(self) -> None:
        seed_paths = [
            r"C:\Music\Seed\Seed One.flac",
            r"C:\Music\Seed\Seed Two.flac",
            r"C:\Music\Seed\Seed Three.flac",
        ]
        cand_a = r"C:\Music\Pool\Candidate A.flac"
        cand_b = r"C:\Music\Pool\Candidate B.flac"
        cand_c = r"C:\Music\Pool\Candidate C.flac"
        meta = {
            "tracks": {
                seed_paths[0]: {
                    "title": "Seed One",
                    "artist": "Artist",
                    "bpm": 128.0,
                    "key": "8A",
                    "mytags": ["Warm-up"],
                    "embedding": "seed-1.npy",
                },
                seed_paths[1]: {
                    "title": "Seed Two",
                    "artist": "Artist",
                    "bpm": 128.0,
                    "key": "8A",
                    "mytags": ["Warm-up"],
                    "embedding": "seed-2.npy",
                },
                seed_paths[2]: {
                    "title": "Seed Three",
                    "artist": "Artist",
                    "bpm": 128.0,
                    "key": "8A",
                    "mytags": ["Warm-up"],
                    "embedding": "seed-3.npy",
                },
                cand_a: {
                    "title": "Candidate A",
                    "artist": "Artist",
                    "bpm": 128.0,
                    "key": "8A",
                    "mytags": ["Warm-up"],
                    "embedding": "cand-a.npy",
                },
                cand_b: {
                    "title": "Candidate B",
                    "artist": "Artist",
                    "bpm": 128.0,
                    "key": "8A",
                    "mytags": ["Warm-up"],
                    "embedding": "cand-b.npy",
                },
                cand_c: {
                    "title": "Candidate C",
                    "artist": "Artist",
                    "bpm": 128.0,
                    "key": "8A",
                    "mytags": ["Warm-up"],
                    "embedding": "cand-c.npy",
                },
            }
        }
        seed_playlist = pe.SeedPlaylist(
            source="manual",
            seed_ref="manual",
            playlist_name="Seed Playlist",
            tracks=[
                pe.SeedTrack(rekordbox_path=seed_paths[0], meta_path=seed_paths[0], title="Seed One", artist="Artist", bpm=128.0, key="8A", mytags=["Warm-up"], embedding_path="seed-1.npy"),
                pe.SeedTrack(rekordbox_path=seed_paths[1], meta_path=seed_paths[1], title="Seed Two", artist="Artist", bpm=128.0, key="8A", mytags=["Warm-up"], embedding_path="seed-2.npy"),
                pe.SeedTrack(rekordbox_path=seed_paths[2], meta_path=seed_paths[2], title="Seed Three", artist="Artist", bpm=128.0, key="8A", mytags=["Warm-up"], embedding_path="seed-3.npy"),
            ],
            diagnostics={"seed_tracks_total": 3, "matched_total": 3, "missing_embedding_total": 0, "unmapped_total": 0},
        )
        embedding_map = {
            "seed-1.npy": np.array([1.0, 0.0], dtype=np.float32),
            "seed-2.npy": np.array([0.95, 0.05], dtype=np.float32),
            "seed-3.npy": np.array([0.9, 0.1], dtype=np.float32),
            "cand-a.npy": np.array([0.99, 0.01], dtype=np.float32),
            "cand-b.npy": np.array([0.98, 0.02], dtype=np.float32),
            "cand-c.npy": np.array([0.0, 1.0], dtype=np.float32),
        }

        seed_vec_1 = embedding_map["seed-1.npy"]
        seed_vec_2 = embedding_map["seed-2.npy"]
        seed_vec_3 = embedding_map["seed-3.npy"]
        centroid_vec = np.mean(np.stack([seed_vec_1, seed_vec_2, seed_vec_3], axis=0), axis=0).astype(np.float32)
        centroid_hits = [
            pe.CandidateHit(path=cand_a, distance=0.01),
            pe.CandidateHit(path=cand_b, distance=0.05),
            pe.CandidateHit(path=cand_c, distance=0.10),
        ]
        coverage_hits = {
            tuple(seed_vec_1.tolist()): [pe.CandidateHit(path=cand_a, distance=0.01), pe.CandidateHit(path=cand_b, distance=0.05)],
            tuple(seed_vec_2.tolist()): [pe.CandidateHit(path=cand_a, distance=0.01), pe.CandidateHit(path=cand_c, distance=0.08)],
            tuple(seed_vec_3.tolist()): [pe.CandidateHit(path=cand_a, distance=0.02), pe.CandidateHit(path=cand_c, distance=0.07)],
        }

        def query_side_effect(meta_tracks_arg, query_vec, candidate_pool, exclude_paths):
            if np.allclose(query_vec, centroid_vec):
                return list(centroid_hits)
            key = tuple(np.asarray(query_vec, dtype=np.float32).tolist())
            return list(coverage_hits.get(key, []))

        with (
            mock.patch.object(pe, "load_meta", return_value=meta),
            mock.patch.object(pe, "load_embedding_safe", side_effect=lambda path: embedding_map.get(path)),
            mock.patch.object(pe, "_query_index_or_bruteforce", side_effect=query_side_effect),
        ):
            result = pe.expand_playlist(seed_playlist, target_total=3, candidate_pool=10, diversity=0.8)

        self.assertEqual(result.add_count, 0)
        self.assertEqual(result.target_total, 3)
        self.assertEqual(result.seed_tracks[0].meta_path, seed_paths[0])
        self.assertEqual(result.combined_tracks, seed_paths)
        self.assertEqual(result.diagnostics["clean_seed_tracks_total"], 3)

        with (
            mock.patch.object(pe, "load_meta", return_value=meta),
            mock.patch.object(pe, "load_embedding_safe", side_effect=lambda path: embedding_map.get(path)),
            mock.patch.object(pe, "_query_index_or_bruteforce", side_effect=query_side_effect),
        ):
            expanded = pe.expand_playlist(seed_playlist, target_total=5, candidate_pool=10, diversity=0.8)

        self.assertEqual(expanded.add_count, 2)
        self.assertEqual(expanded.target_total, 5)
        self.assertEqual([track.path for track in expanded.added_tracks], [cand_a, cand_c])
        self.assertEqual(expanded.combined_tracks, seed_paths + [cand_a, cand_c])
        self.assertGreater(expanded.diagnostics["selected_count"], 0)
        self.assertIn("controls_applied", expanded.diagnostics)
        self.assertIn("normalized_weights", expanded.diagnostics)
        self.assertEqual(expanded.added_tracks[0].score, expanded.added_tracks[0].final_score)
        self.assertIn("ann_centroid", expanded.added_tracks[0].component_scores)

    def test_expand_playlist_penalizes_repeat_artist_and_version_patterns(self) -> None:
        seed_paths = [
            r"C:\Music\Seed\Seed One.flac",
            r"C:\Music\Seed\Seed Two.flac",
            r"C:\Music\Seed\Seed Three.flac",
        ]
        repeat_path = r"C:\Music\Pool\A-Repeat.flac"
        distinct_path = r"C:\Music\Pool\B-Other.flac"
        meta = {
            "tracks": {
                seed_paths[0]: {
                    "title": "Warmup Song (Original Mix)",
                    "artist": "DJ One",
                    "bpm": 128.0,
                    "key": "8A",
                    "mytags": ["Warm-up"],
                    "embedding": "seed-1.npy",
                },
                seed_paths[1]: {
                    "title": "Warmup Song (Original Mix)",
                    "artist": "DJ One",
                    "bpm": 128.0,
                    "key": "8A",
                    "mytags": ["Warm-up"],
                    "embedding": "seed-2.npy",
                },
                seed_paths[2]: {
                    "title": "Warmup Song (Original Mix)",
                    "artist": "DJ One",
                    "bpm": 128.0,
                    "key": "8A",
                    "mytags": ["Warm-up"],
                    "embedding": "seed-3.npy",
                },
                repeat_path: {
                    "title": "Warmup Song (Original Mix)",
                    "artist": "DJ One",
                    "bpm": 128.0,
                    "key": "8A",
                    "mytags": ["Warm-up"],
                    "embedding": "repeat.npy",
                },
                distinct_path: {
                    "title": "Different Lift",
                    "artist": "DJ Two",
                    "bpm": 128.0,
                    "key": "8A",
                    "mytags": ["Warm-up"],
                    "embedding": "distinct.npy",
                },
            }
        }
        seed_playlist = pe.SeedPlaylist(
            source="manual",
            seed_ref="manual",
            playlist_name="Seed Playlist",
            tracks=[
                pe.SeedTrack(
                    rekordbox_path=seed_paths[0],
                    meta_path=seed_paths[0],
                    title="Warmup Song (Original Mix)",
                    artist="DJ One",
                    bpm=128.0,
                    key="8A",
                    mytags=["Warm-up"],
                    embedding_path="seed-1.npy",
                ),
                pe.SeedTrack(
                    rekordbox_path=seed_paths[1],
                    meta_path=seed_paths[1],
                    title="Warmup Song (Original Mix)",
                    artist="DJ One",
                    bpm=128.0,
                    key="8A",
                    mytags=["Warm-up"],
                    embedding_path="seed-2.npy",
                ),
                pe.SeedTrack(
                    rekordbox_path=seed_paths[2],
                    meta_path=seed_paths[2],
                    title="Warmup Song (Original Mix)",
                    artist="DJ One",
                    bpm=128.0,
                    key="8A",
                    mytags=["Warm-up"],
                    embedding_path="seed-3.npy",
                ),
            ],
            diagnostics={"seed_tracks_total": 3, "matched_total": 3, "missing_embedding_total": 0, "unmapped_total": 0},
        )
        embedding_map = {
            "seed-1.npy": np.array([1.0, 0.0], dtype=np.float32),
            "seed-2.npy": np.array([1.0, 0.0], dtype=np.float32),
            "seed-3.npy": np.array([1.0, 0.0], dtype=np.float32),
            "repeat.npy": np.array([1.0, 0.0], dtype=np.float32),
            "distinct.npy": np.array([1.0, 0.0], dtype=np.float32),
        }

        with (
            mock.patch.object(pe, "load_meta", return_value=meta),
            mock.patch.object(pe, "load_embedding_safe", side_effect=lambda path: embedding_map.get(path)),
            mock.patch.object(pe, "_query_index_or_bruteforce", side_effect=lambda meta_tracks_arg, query_vec, candidate_pool, exclude_paths: [
                pe.CandidateHit(path=repeat_path, distance=0.02),
                pe.CandidateHit(path=distinct_path, distance=0.02),
            ]),
        ):
            result = pe.expand_playlist(seed_playlist, target_total=5, candidate_pool=10, diversity=0.0)

        self.assertEqual([track.path for track in result.added_tracks], [distinct_path, repeat_path])
        self.assertIn("anti_repetition_penalty_total", result.diagnostics)
        self.assertGreater(result.diagnostics["anti_repetition_penalty_total"], 0.0)
        self.assertGreater(result.added_tracks[1].component_scores.get("anti_repetition", 0.0), 0.0)
        self.assertIn("artist_repeat", result.added_tracks[1].reasons)
        self.assertIn("title_repeat", result.added_tracks[1].reasons)
        self.assertIn("version_repeat", result.added_tracks[1].reasons)

    def test_prepare_and_rerank_reuses_cached_candidate_pool(self) -> None:
        seed_paths = [
            r"C:\Music\Seed\Seed One.flac",
            r"C:\Music\Seed\Seed Two.flac",
            r"C:\Music\Seed\Seed Three.flac",
        ]
        cand_a = r"C:\Music\Pool\Candidate A.flac"
        cand_b = r"C:\Music\Pool\Candidate B.flac"
        meta = {
            "tracks": {
                seed_paths[0]: {"bpm": 128.0, "key": "8A", "mytags": ["Warm-up"], "embedding": "seed-1.npy"},
                seed_paths[1]: {"bpm": 128.0, "key": "8A", "mytags": ["Warm-up"], "embedding": "seed-2.npy"},
                seed_paths[2]: {"bpm": 128.0, "key": "8A", "mytags": ["Warm-up"], "embedding": "seed-3.npy"},
                cand_a: {"bpm": 128.0, "key": "8A", "mytags": ["Warm-up"], "embedding": "cand-a.npy"},
                cand_b: {"bpm": 128.0, "key": "8A", "mytags": ["Warm-up"], "embedding": "cand-b.npy"},
            }
        }
        seed_playlist = pe.SeedPlaylist(
            source="manual",
            seed_ref="manual",
            playlist_name="Seed Playlist",
            tracks=[
                pe.SeedTrack(rekordbox_path=seed_paths[0], meta_path=seed_paths[0], bpm=128.0, key="8A", mytags=["Warm-up"], embedding_path="seed-1.npy"),
                pe.SeedTrack(rekordbox_path=seed_paths[1], meta_path=seed_paths[1], bpm=128.0, key="8A", mytags=["Warm-up"], embedding_path="seed-2.npy"),
                pe.SeedTrack(rekordbox_path=seed_paths[2], meta_path=seed_paths[2], bpm=128.0, key="8A", mytags=["Warm-up"], embedding_path="seed-3.npy"),
            ],
            diagnostics={"seed_tracks_total": 3, "matched_total": 3, "missing_embedding_total": 0, "unmapped_total": 0},
        )
        embedding_map = {
            "seed-1.npy": np.array([1.0, 0.0], dtype=np.float32),
            "seed-2.npy": np.array([0.9, 0.1], dtype=np.float32),
            "seed-3.npy": np.array([0.8, 0.2], dtype=np.float32),
            "cand-a.npy": np.array([0.99, 0.01], dtype=np.float32),
            "cand-b.npy": np.array([0.2, 0.8], dtype=np.float32),
        }
        centroid_vec = np.mean(
            np.stack([embedding_map["seed-1.npy"], embedding_map["seed-2.npy"], embedding_map["seed-3.npy"]], axis=0),
            axis=0,
        ).astype(np.float32)
        centroid_hits = [pe.CandidateHit(path=cand_a, distance=0.01), pe.CandidateHit(path=cand_b, distance=0.1)]
        coverage_hits = {
            tuple(embedding_map["seed-1.npy"].tolist()): [pe.CandidateHit(path=cand_a, distance=0.01)],
            tuple(embedding_map["seed-2.npy"].tolist()): [pe.CandidateHit(path=cand_a, distance=0.02), pe.CandidateHit(path=cand_b, distance=0.2)],
            tuple(embedding_map["seed-3.npy"].tolist()): [pe.CandidateHit(path=cand_a, distance=0.02)],
        }

        def query_side_effect(meta_tracks_arg, query_vec, candidate_pool, exclude_paths):
            if np.allclose(query_vec, centroid_vec):
                return list(centroid_hits)
            return list(coverage_hits.get(tuple(np.asarray(query_vec, dtype=np.float32).tolist()), []))

        with (
            mock.patch.object(pe, "load_meta", return_value=meta),
            mock.patch.object(pe, "load_embedding_safe", side_effect=lambda path: embedding_map.get(path)),
            mock.patch.object(pe, "_query_index_or_bruteforce", side_effect=query_side_effect),
        ):
            workspace = pe.prepare_playlist_expansion(seed_playlist, candidate_pool=10)

        with mock.patch.object(pe, "_query_index_or_bruteforce", side_effect=AssertionError("ANN requery not allowed")):
            reranked = pe.rerank_playlist_expansion(workspace, add_count=1)

        self.assertEqual([track.path for track in reranked.added_tracks], [cand_a])
        self.assertEqual(reranked.diagnostics["candidate_pool_total"], len(workspace.candidates))
        self.assertIn("controls_applied", reranked.diagnostics)

    def test_expand_playlist_rejects_inconsistent_counts(self) -> None:
        seed_paths = [
            r"C:\Music\Seed\Seed One.flac",
            r"C:\Music\Seed\Seed Two.flac",
            r"C:\Music\Seed\Seed Three.flac",
        ]
        meta = {
            "tracks": {
                seed_paths[0]: {"embedding": "seed-1.npy", "bpm": 128.0, "key": "8A"},
                seed_paths[1]: {"embedding": "seed-2.npy", "bpm": 128.0, "key": "8A"},
                seed_paths[2]: {"embedding": "seed-3.npy", "bpm": 128.0, "key": "8A"},
            }
        }
        seed_playlist = pe.SeedPlaylist(
            source="manual",
            seed_ref="manual",
            playlist_name="Seed Playlist",
            tracks=[pe.SeedTrack(rekordbox_path=path, meta_path=path, embedding_path=f"seed-{idx}.npy") for idx, path in enumerate(seed_paths, start=1)],
        )

        with mock.patch.object(pe, "load_meta", return_value=meta), mock.patch.object(
            pe, "load_embedding_safe", return_value=np.array([1.0, 0.0], dtype=np.float32)
        ):
            with self.assertRaises(ValueError):
                pe.expand_playlist(seed_playlist, add_count=1, target_total=5)

    def test_expand_playlist_fails_when_fewer_than_three_embedded_seeds(self) -> None:
        seed_paths = [
            r"C:\Music\Seed\Seed One.flac",
            r"C:\Music\Seed\Seed Two.flac",
            r"C:\Music\Seed\Seed Three.flac",
        ]
        meta = {
            "tracks": {
                seed_paths[0]: {"embedding": "seed-1.npy", "bpm": 128.0, "key": "8A"},
                seed_paths[1]: {"bpm": 128.0, "key": "8A"},
                seed_paths[2]: {"bpm": 128.0, "key": "8A"},
            }
        }

        with mock.patch.object(pe, "load_meta", return_value=meta), mock.patch.object(
            pe, "load_embedding_safe", return_value=np.array([1.0, 0.0], dtype=np.float32)
        ):
            with self.assertRaises(ValueError):
                pe.expand_playlist(seed_paths, target_total=5)

    def test_write_expansion_xml_preserves_seed_order_then_additions(self) -> None:
        seed_paths = [
            r"C:\Music\Seed\Seed One.flac",
            r"C:\Music\Seed\Seed Two.flac",
            r"C:\Music\Seed\Seed Three.flac",
        ]
        added_paths = [
            r"C:\Music\Pool\Candidate A.flac",
            r"C:\Music\Pool\Candidate C.flac",
        ]
        meta = {
            "tracks": {
                path: {"title": pathlib.Path(path).stem, "artist": "Artist", "embedding": f"{idx}.npy"}
                for idx, path in enumerate(seed_paths + added_paths, start=1)
            }
        }
        result = pe.ExpansionResult(
            seed_tracks=[pe.SeedTrack(rekordbox_path=path, meta_path=path, embedding_path=f"{idx}.npy") for idx, path in enumerate(seed_paths, start=1)],
            added_tracks=[pe.ExpandedTrack(path=path, score=1.0) for path in added_paths],
            combined_tracks=seed_paths + added_paths,
            diagnostics={},
            target_total=5,
            add_count=2,
            strategy="centroid",
        )

        with tempfile.TemporaryDirectory() as td:
            out_path = pathlib.Path(td) / "nested" / "expanded.xml"
            pe.write_expansion_xml(result, out_path=str(out_path), playlist_name="Expanded", meta=meta)
            root = ET.parse(out_path).getroot()

        keys = [track.get("Key") for track in root.findall("./PLAYLISTS/NODE/NODE/TRACK")]
        self.assertEqual(len(keys), 5)
        self.assertTrue(keys[0].endswith("Seed%20One.flac"))
        self.assertTrue(keys[1].endswith("Seed%20Two.flac"))
        self.assertTrue(keys[2].endswith("Seed%20Three.flac"))
        self.assertTrue(keys[3].endswith("Candidate%20A.flac"))
        self.assertTrue(keys[4].endswith("Candidate%20C.flac"))

    def test_playlist_expand_cli_writes_preview_and_export(self) -> None:
        runner = CliRunner()
        seed_paths = [
            r"C:\Music\Seed\Seed One.flac",
            r"C:\Music\Seed\Seed Two.flac",
            r"C:\Music\Seed\Seed Three.flac",
        ]
        seed_playlist = pe.SeedPlaylist(
            source="db",
            seed_ref="Warmup",
            playlist_name="Warmup",
            tracks=[pe.SeedTrack(rekordbox_path=path, meta_path=path, embedding_path=f"{idx}.npy") for idx, path in enumerate(seed_paths, start=1)],
            diagnostics={"seed_tracks_total": 3, "matched_total": 3, "missing_embedding_total": 0, "unmapped_total": 0},
        )
        result = pe.ExpansionResult(
            seed_tracks=seed_playlist.tracks,
            added_tracks=[
                pe.ExpandedTrack(
                    path=r"C:\Music\Pool\Candidate A.flac",
                    score=0.9,
                    base_score=0.92,
                    final_score=0.9,
                    component_scores={"ann_centroid": 0.95, "tag_match": 0.2},
                )
            ],
            combined_tracks=seed_paths + [r"C:\Music\Pool\Candidate A.flac"],
            diagnostics={
                "clean_seed_tracks_total": 3,
                "added_tracks_total": 1,
                "combined_tracks_total": 4,
                "requested_add_count": 1,
                "requested_target_total": 4,
                "strategy": "blend",
                "mode": "balanced",
                "controls_applied": {
                    "mode": "balanced",
                    "strategy": "blend",
                    "filters": {"key_mode": "filter"},
                },
                "normalized_weights": {
                    "ann_centroid": 0.3,
                    "ann_seed_coverage": 0.2,
                    "group_match": 0.16,
                    "bpm_match": 0.12,
                    "key_match": 0.08,
                    "tag_match": 0.14,
                },
                "seed_loader_diagnostics": seed_playlist.diagnostics,
            },
            target_total=4,
            add_count=1,
            strategy="blend",
        )

        with tempfile.TemporaryDirectory() as td:
            preview_path = pathlib.Path(td) / "preview.json"
            xml_path = pathlib.Path(td) / "expanded.xml"
            with (
                mock.patch.object(pe, "load_rekordbox_playlist", return_value=seed_playlist),
                mock.patch.object(pe, "expand_playlist", return_value=result) as expand_playlist,
                mock.patch.object(pe, "write_expansion_xml") as write_xml,
            ):
                invoke = runner.invoke(
                    cli.app,
                    [
                        "playlist-expand",
                        "--playlist",
                        "Warmup",
                        "--target-total",
                        "4",
                        "--key-filter",
                        "--preview-json",
                        str(preview_path),
                        "--out-xml",
                        str(xml_path),
                    ],
                )
            self.assertEqual(invoke.exit_code, 0, msg=invoke.stdout)
            self.assertTrue(preview_path.exists())
            payload = json.loads(preview_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["target_total"], 4)
            self.assertEqual(payload["diagnostics"]["controls_applied"]["mode"], "balanced")
            self.assertEqual(payload["added_tracks"][0]["component_scores"]["ann_centroid"], 0.95)
            self.assertEqual(expand_playlist.call_args.kwargs["mode"], "balanced")
            self.assertEqual(expand_playlist.call_args.kwargs["strategy"], "blend")
            self.assertEqual(expand_playlist.call_args.kwargs["filters"], {"key_mode": "filter"})
            write_xml.assert_called_once()

    def test_playlist_expand_cli_passes_explicit_overrides(self) -> None:
        runner = CliRunner()
        seed_playlist = pe.SeedPlaylist(
            source="db",
            seed_ref="Warmup",
            playlist_name="Warmup",
            tracks=[
                pe.SeedTrack(
                    rekordbox_path=r"C:\Music\Seed\Seed One.flac",
                    meta_path=r"C:\Music\Seed\Seed One.flac",
                    embedding_path="1.npy",
                ),
                pe.SeedTrack(
                    rekordbox_path=r"C:\Music\Seed\Seed Two.flac",
                    meta_path=r"C:\Music\Seed\Seed Two.flac",
                    embedding_path="2.npy",
                ),
                pe.SeedTrack(
                    rekordbox_path=r"C:\Music\Seed\Seed Three.flac",
                    meta_path=r"C:\Music\Seed\Seed Three.flac",
                    embedding_path="3.npy",
                ),
            ],
            diagnostics={"seed_tracks_total": 3, "matched_total": 3, "missing_embedding_total": 0, "unmapped_total": 0},
        )
        result = pe.ExpansionResult(
            seed_tracks=seed_playlist.tracks,
            added_tracks=[],
            combined_tracks=[track.meta_path for track in seed_playlist.tracks if track.meta_path],
            diagnostics={
                "clean_seed_tracks_total": 3,
                "added_tracks_total": 0,
                "combined_tracks_total": 3,
                "requested_add_count": 0,
                "requested_target_total": 3,
                "strategy": "coverage",
                "mode": "adventurous",
                "controls_applied": {
                    "mode": "adventurous",
                    "strategy": "coverage",
                    "candidate_pool": 400,
                },
                "normalized_weights": {
                    "ann_centroid": 0.4,
                    "ann_seed_coverage": 0.2,
                    "group_match": 0.1,
                    "bpm_match": 0.2,
                    "key_match": 0.05,
                    "tag_match": 0.05,
                },
                "seed_loader_diagnostics": seed_playlist.diagnostics,
            },
            target_total=3,
            add_count=0,
            strategy="coverage",
            mode="adventurous",
        )

        with (
            mock.patch.object(pe, "load_rekordbox_playlist", return_value=seed_playlist),
            mock.patch.object(pe, "expand_playlist", return_value=result) as expand_playlist,
        ):
            invoke = runner.invoke(
                cli.app,
                [
                    "playlist-expand",
                    "--playlist",
                    "Warmup",
                    "--target-total",
                    "3",
                    "--mode",
                    "adventurous",
                    "--strategy",
                    "coverage",
                    "--candidate-pool",
                    "400",
                    "--diversity",
                    "0.55",
                    "--tempo-pct",
                    "10",
                    "--allow-doubletime",
                    "--key-mode",
                    "soft",
                    "--w-ann-centroid",
                    "0.4",
                    "--w-ann-seed-coverage",
                    "0.2",
                    "--w-group-match",
                    "0.1",
                    "--w-bpm",
                    "0.2",
                    "--w-key",
                    "0.05",
                    "--w-tags",
                    "0.05",
                ],
            )

        self.assertEqual(invoke.exit_code, 0, msg=invoke.stdout)
        self.assertEqual(expand_playlist.call_args.kwargs["mode"], "adventurous")
        self.assertEqual(expand_playlist.call_args.kwargs["strategy"], "coverage")
        self.assertEqual(expand_playlist.call_args.kwargs["candidate_pool"], 400)
        self.assertEqual(expand_playlist.call_args.kwargs["diversity"], 0.55)
        self.assertEqual(
            expand_playlist.call_args.kwargs["filters"],
            {"tempo_pct": 10.0, "allow_doubletime": True, "key_mode": "soft"},
        )
        self.assertEqual(
            expand_playlist.call_args.kwargs["weights"],
            {
                "ann_centroid": 0.4,
                "ann_seed_coverage": 0.2,
                "group_match": 0.1,
                "bpm_match": 0.2,
                "key_match": 0.05,
                "tag_match": 0.05,
            },
        )

    def test_playlist_expand_cli_falls_back_to_xml_when_db_load_fails(self) -> None:
        runner = CliRunner()
        seed_playlist = pe.SeedPlaylist(
            source="xml",
            seed_ref="Warmup",
            playlist_name="Warmup",
            tracks=[
                pe.SeedTrack(rekordbox_path=r"C:\Music\Seed\Seed One.flac", meta_path=r"C:\Music\Seed\Seed One.flac", embedding_path="1.npy"),
                pe.SeedTrack(rekordbox_path=r"C:\Music\Seed\Seed Two.flac", meta_path=r"C:\Music\Seed\Seed Two.flac", embedding_path="2.npy"),
                pe.SeedTrack(rekordbox_path=r"C:\Music\Seed\Seed Three.flac", meta_path=r"C:\Music\Seed\Seed Three.flac", embedding_path="3.npy"),
            ],
            diagnostics={"seed_tracks_total": 3, "matched_total": 3, "missing_embedding_total": 0, "unmapped_total": 0},
        )
        result = pe.ExpansionResult(
            seed_tracks=seed_playlist.tracks,
            added_tracks=[],
            combined_tracks=[track.meta_path for track in seed_playlist.tracks if track.meta_path],
            diagnostics={
                "clean_seed_tracks_total": 3,
                "added_tracks_total": 0,
                "combined_tracks_total": 3,
                "requested_add_count": 0,
                "requested_target_total": 3,
                "strategy": "centroid",
                "mode": "balanced",
                "seed_loader_diagnostics": seed_playlist.diagnostics,
            },
            target_total=3,
            add_count=0,
            strategy="centroid",
        )

        with tempfile.TemporaryDirectory() as td:
            xml_path = pathlib.Path(td) / "fallback.xml"
            xml_path.write_text("<xml />", encoding="utf-8")
            with (
                mock.patch.object(pe, "load_rekordbox_playlist", side_effect=[RuntimeError("db unavailable"), seed_playlist]) as load_playlist,
                mock.patch.object(pe, "expand_playlist", return_value=result),
            ):
                invoke = runner.invoke(
                    cli.app,
                    [
                        "playlist-expand",
                        "--playlist",
                        "Warmup",
                        "--target-total",
                        "3",
                        "--xml-path",
                        str(xml_path),
                    ],
                )

        self.assertEqual(invoke.exit_code, 0, msg=invoke.stdout)
        self.assertEqual(load_playlist.call_count, 2)
        self.assertEqual(load_playlist.call_args_list[0].kwargs["source"], "db")
        self.assertEqual(load_playlist.call_args_list[1].kwargs["source"], "xml")


if __name__ == "__main__":
    import unittest

    unittest.main()
