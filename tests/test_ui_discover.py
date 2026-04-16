import unittest
from types import SimpleNamespace
from unittest import mock

from rbassist.ui.pages.discover import (
    DiscoverPage,
    _should_apply_refresh_result,
    _should_continue_refresh_drain,
    _should_start_refresh_task,
)


class DiscoverPageHelperTests(unittest.TestCase):
    def test_should_start_refresh_task_only_when_no_task_is_running(self) -> None:
        self.assertTrue(_should_start_refresh_task(running=False))
        self.assertFalse(_should_start_refresh_task(running=True))

    def test_should_apply_refresh_result_only_for_latest_non_browse_request(self) -> None:
        self.assertTrue(
            _should_apply_refresh_result(request_id=3, latest_request_id=3, browse_mode=False)
        )
        self.assertFalse(
            _should_apply_refresh_result(request_id=2, latest_request_id=3, browse_mode=False)
        )
        self.assertFalse(
            _should_apply_refresh_result(request_id=3, latest_request_id=3, browse_mode=True)
        )

    def test_should_continue_refresh_drain_only_when_newer_request_exists(self) -> None:
        self.assertTrue(
            _should_continue_refresh_drain(
                completed_request_id=2,
                latest_request_id=3,
                browse_mode=False,
            )
        )
        self.assertFalse(
            _should_continue_refresh_drain(
                completed_request_id=3,
                latest_request_id=3,
                browse_mode=False,
            )
        )
        self.assertFalse(
            _should_continue_refresh_drain(
                completed_request_id=2,
                latest_request_id=3,
                browse_mode=True,
            )
        )

    def test_get_recommendations_delegates_to_gui_neutral_service(self) -> None:
        page = SimpleNamespace(
            state=SimpleNamespace(
                meta={"tracks": {}},
                filters={"tempo_pct": 6.0},
                weights={"ann": 1.0},
            )
        )

        with mock.patch(
            "rbassist.ui.pages.discover.build_recommendation_rows",
            return_value=[{"path": "candidate.mp3"}],
        ) as build_mock:
            rows = DiscoverPage._get_recommendations(page, "seed.mp3")

        self.assertEqual(rows, [{"path": "candidate.mp3"}])
        build_mock.assert_called_once_with(
            seed_path="seed.mp3",
            top=50,
            meta={"tracks": {}},
            filters={"tempo_pct": 6.0},
            weights={"ann": 1.0},
        )


if __name__ == "__main__":
    unittest.main()
