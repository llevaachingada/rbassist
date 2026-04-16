import pathlib
import tempfile
import unittest

from rbassist.keeper_manifest import build_keeper_manifest, build_keeper_manifest_markdown, write_keeper_manifest


class KeeperManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = pathlib.Path(__file__).resolve().parents[1]

    def test_manifest_includes_expected_workstreams(self) -> None:
        manifest = build_keeper_manifest(repo=self.repo, include_live_state=False)
        workstream_ids = {item["id"] for item in manifest["workstreams"]}
        self.assertEqual(
            workstream_ids,
            {
                "rbassist-meta-hygiene",
                "rbassist-rekordbox-safe-relink",
                "rbassist-duplicate-remediation",
                "rbassist-library-rollout-qa",
            },
        )
        inventory = {item["path"]: item for item in manifest["active_file_inventory"]}
        self.assertIn("rbassist/health.py", inventory)
        self.assertIn("rbassist/rekordbox_audit.py", inventory)
        self.assertIn("scripts/run_music_root_background_maintenance.py", inventory)
        self.assertTrue(inventory["rbassist/health.py"]["exists"])

    def test_markdown_mentions_core_sections(self) -> None:
        manifest = build_keeper_manifest(repo=self.repo, include_live_state=False)
        text = build_keeper_manifest_markdown(manifest)
        self.assertIn("Keeper Manifest: Active Files", text)
        self.assertIn("rbassist-meta-hygiene", text)
        self.assertIn("rbassist-rekordbox-safe-relink", text)
        self.assertIn("Local Runtime Keepers", text)

    def test_write_keeper_manifest_outputs_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            outputs = write_keeper_manifest(
                repo=self.repo,
                out_json=base / "keeper.json",
                out_md=base / "keeper.md",
                include_live_state=False,
            )
            self.assertTrue(outputs["json"].exists())
            self.assertTrue(outputs["md"].exists())
            self.assertIn("rbassist-library-rollout-qa", outputs["md"].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
