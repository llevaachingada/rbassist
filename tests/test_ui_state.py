import unittest
from unittest import mock

from rbassist.ui import state as ui_state


class AppStateTests(unittest.TestCase):
    def test_refresh_health_uses_configured_music_roots(self) -> None:
        app = ui_state.AppState(meta={'tracks': {}}, music_folders=[r'C:\Music\A', r'C:\Music\B'])
        with mock.patch.object(ui_state, 'audit_meta_health', return_value={'counts': {}}) as audit_mock,              mock.patch.object(ui_state, 'suggest_rewrite_pairs', return_value=[]):
            app.refresh_health()
        self.assertEqual(audit_mock.call_args.kwargs['roots'], [r'C:\Music\A', r'C:\Music\B'])

    def test_current_music_roots_falls_back_to_defaults(self) -> None:
        app = ui_state.AppState(meta={'tracks': {}}, music_folders=[])
        with mock.patch.object(ui_state, 'default_music_roots', return_value=[r'C:\Users\hunte\Music']):
            self.assertEqual(app.current_music_roots(), [r'C:\Users\hunte\Music'])


if __name__ == '__main__':
    unittest.main()
