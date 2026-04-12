import unittest

from rbassist.ui.pages.discover import (
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


if __name__ == "__main__":
    unittest.main()
