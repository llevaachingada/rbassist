from __future__ import annotations

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, mock

from rbassist import playlist_expand as pe
from rbassist.ui.pages import crate_expander as ce


class _Widget:
    def __init__(self, value=None):
        self.value = value
        self.text = ""
        self.options = {}
        self.updated = 0

    def update(self) -> None:
        self.updated += 1


class CrateExpanderAsyncTests(IsolatedAsyncioTestCase):
    def test_build_controls_passes_advanced_matching_switches(self) -> None:
        page = ce.CrateExpander()
        page.preset_toggle = _Widget("balanced")
        page.strategy_toggle = _Widget("blend")
        page.ann_centroid_slider = _Widget(0.3)
        page.ann_seed_coverage_slider = _Widget(0.2)
        page.group_match_slider = _Widget(0.1)
        page.bpm_match_slider = _Widget(0.1)
        page.key_match_slider = _Widget(0.2)
        page.tag_match_slider = _Widget(0.1)
        page.diversity_slider = _Widget(0.25)
        page.tempo_slider = _Widget(6.0)
        page.doubletime_switch = _Widget(True)
        page.key_mode_toggle = _Widget("soft")
        page.require_tags_input = _Widget("")
        page.candidate_pool_input = _Widget(250)
        page.harmonic_key_switch = _Widget(True)
        page.section_scores_switch = _Widget(True)

        controls = page._build_controls()

        self.assertTrue(controls.use_harmonic_key_scores)
        self.assertTrue(controls.use_section_scores)

    def test_workspace_signature_includes_component_score_controls(self) -> None:
        page = ce.CrateExpander()
        page.preset_toggle = _Widget("balanced")
        page.strategy_toggle = _Widget("blend")
        page.ann_centroid_slider = _Widget(0.3)
        page.ann_seed_coverage_slider = _Widget(0.2)
        page.group_match_slider = _Widget(0.1)
        page.bpm_match_slider = _Widget(0.1)
        page.key_match_slider = _Widget(0.2)
        page.tag_match_slider = _Widget(0.1)
        page.diversity_slider = _Widget(0.25)
        page.tempo_slider = _Widget(6.0)
        page.doubletime_switch = _Widget(True)
        page.key_mode_toggle = _Widget("soft")
        page.require_tags_input = _Widget("")
        page.candidate_pool_input = _Widget(250)
        page.harmonic_key_switch = _Widget(False)
        page.section_scores_switch = _Widget(False)
        page.selected_seeds = ["seed"]

        baseline = page._workspace_signature()
        page.harmonic_key_switch.value = True
        harmonic = page._workspace_signature()
        page.section_scores_switch.value = True
        section = page._workspace_signature()
        page.tempo_slider.value = 8.0
        tempo = page._workspace_signature()

        self.assertNotEqual(baseline, harmonic)
        self.assertNotEqual(harmonic, section)
        self.assertNotEqual(section, tempo)

    async def test_load_selected_rekordbox_playlist_uses_worker_and_updates_state(self) -> None:
        page = ce.CrateExpander()
        page.rekordbox_playlist_select = _Widget("db:7")
        page.rekordbox_source_toggle = _Widget("db")
        page.rekordbox_xml_input = _Widget("")
        page.rekordbox_playlist_items = [
            {"source": "db", "path": "Folder/Warmup", "name": "Warmup", "id": 7},
        ]
        page.seed_count_label = _Widget()
        page.status_label = _Widget()
        page.loaded_playlist_label = _Widget()
        page._render_seeds_callback = lambda: None
        page._clear_results_table = lambda: None
        page._update_count_hint = lambda: None

        seed_playlist = pe.SeedPlaylist(
            source="db",
            seed_ref="7",
            playlist_name="Warmup",
            tracks=[
                pe.SeedTrack(
                    rekordbox_path=r"C:\Music\Seed One.flac",
                    meta_path=r"C:\Music\Seed One.flac",
                    title="Seed One",
                    artist="Artist",
                    bpm=128.0,
                    embedding_path="seed-one.npy",
                )
            ],
            diagnostics={"matched_total": 1, "missing_embedding_total": 0, "unmapped_total": 0},
        )

        async def _to_thread(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        with (
            mock.patch.object(ce.asyncio, "to_thread", side_effect=_to_thread) as to_thread,
            mock.patch.object(ce, "load_rekordbox_playlist", return_value=seed_playlist) as load_playlist,
            mock.patch.object(ce.ui, "notify") as notify,
        ):
            await page._load_selected_rekordbox_playlist()

        to_thread.assert_called_once()
        load_playlist.assert_called_once_with(7, source="db", playlist_path="Folder/Warmup", xml_path=None)
        self.assertEqual(page.selected_seeds, [r"C:\Music\Seed One.flac"])
        self.assertEqual(page.loaded_playlist_name, "Warmup")
        self.assertIn("Loaded Warmup", page.status_label.text)
        self.assertEqual(page.loaded_playlist_label.text, "Loaded playlist: Warmup")
        notify.assert_called_once()

    async def test_refresh_rekordbox_playlists_uses_worker_and_updates_options(self) -> None:
        page = ce.CrateExpander()
        page.rekordbox_source_toggle = _Widget("db")
        page.rekordbox_xml_input = _Widget("")
        page.rekordbox_playlist_select = _Widget()
        page.rekordbox_status_label = _Widget()
        page.rekordbox_filter_input = _Widget("")
        page.rekordbox_playlist_items = []

        items = [
            {"source": "db", "path": "Folder/Warmup", "name": "Warmup", "id": 7},
            {"source": "db", "path": "Folder/Peak", "name": "Peak", "id": 8},
        ]

        async def _to_thread(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        with (
            mock.patch.object(ce.asyncio, "to_thread", side_effect=_to_thread) as to_thread,
            mock.patch.object(ce, "list_rekordbox_playlists", return_value=items),
            mock.patch.object(ce.ui, "notify") as notify,
        ):
            await page._refresh_rekordbox_playlists()

        to_thread.assert_called_once()
        self.assertEqual(page.rekordbox_playlist_items, items)
        self.assertEqual(page.rekordbox_playlist_select.options["db:7"], "Folder/Warmup")
        self.assertEqual(page.rekordbox_playlist_select.value, "db:7")
        self.assertEqual(page.rekordbox_status_label.text, "2 playlists available")
        notify.assert_called_once()

    async def test_load_selected_rekordbox_playlist_uses_id_for_names_with_slashes(self) -> None:
        page = ce.CrateExpander()
        page.rekordbox_playlist_select = _Widget("db:42")
        page.rekordbox_source_toggle = _Widget("db")
        page.rekordbox_xml_input = _Widget("")
        page.rekordbox_playlist_items = [
            {"source": "db", "path": "DOWNLOAD CHUNX/radio 10/22", "name": "radio 10/22", "id": 42},
        ]
        page.seed_count_label = _Widget()
        page.status_label = _Widget()
        page.loaded_playlist_label = _Widget()
        page._render_seeds_callback = lambda: None
        page._clear_results_table = lambda: None
        page._update_count_hint = lambda: None

        seed_playlist = pe.SeedPlaylist(
            source="db",
            seed_ref="42",
            playlist_name="radio 10/22",
            tracks=[
                pe.SeedTrack(
                    rekordbox_path=r"C:\Music\Seed One.flac",
                    meta_path=r"C:\Music\Seed One.flac",
                    title="Seed One",
                    artist="Artist",
                    bpm=128.0,
                    embedding_path="seed-one.npy",
                )
            ],
            diagnostics={"matched_total": 1, "missing_embedding_total": 0, "unmapped_total": 0},
        )

        async def _to_thread(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        with (
            mock.patch.object(ce.asyncio, "to_thread", side_effect=_to_thread),
            mock.patch.object(ce, "load_rekordbox_playlist", return_value=seed_playlist) as load_playlist,
            mock.patch.object(ce.ui, "notify"),
        ):
            await page._load_selected_rekordbox_playlist()

        load_playlist.assert_called_once_with(
            42,
            source="db",
            playlist_path="DOWNLOAD CHUNX/radio 10/22",
            xml_path=None,
        )
