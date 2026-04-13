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
