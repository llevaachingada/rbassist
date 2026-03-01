import importlib.util
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


def _load_script_module(name: str, relative_path: str):
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    module_path = repo_root / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run_embed_chunks = _load_script_module("test_run_embed_chunks_module", "scripts/run_embed_chunks.py")


def _result(module, *, status: str, device: str, checkpoint_path: pathlib.Path, failed: int = 0, succeeded: int = 0):
    return module.ChunkAttemptResult(
        status=status,
        returncode=0 if status in {"ok", "completed_with_failures"} else 1,
        checkpoint_path=checkpoint_path,
        failed_log_path=None,
        checkpoint={},
        error_counts={},
        queued=failed + succeeded,
        succeeded=succeeded,
        failed=failed,
        output="",
        device=device,
    )


class RunEmbedChunksTests(unittest.TestCase):
    def test_read_chunk_paths_strips_utf8_bom(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            chunk_path = base / "paths.txt"
            chunk_path.write_text("\ufeffa.mp3\nb.mp3\n", encoding="utf-8")

            loaded = run_embed_chunks._read_chunk_paths(chunk_path)

            self.assertEqual(loaded, ["a.mp3", "b.mp3"])

    def test_classify_attempt_detects_cuda_fault_from_failed_log(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            checkpoint = base / "embed_checkpoint_part001.cuda.json"
            failed_log = checkpoint.with_name(f"{checkpoint.stem}_failed.jsonl")
            checkpoint.write_text(
                '{"status":"completed","counters":{"queued":1,"succeeded":0,"failed":1}}',
                encoding="utf-8",
            )
            failed_log.write_text(
                '{"error":"RuntimeError(\\"CUDA error: an illegal memory access was encountered\\")"}\n',
                encoding="utf-8",
            )

            result = run_embed_chunks._classify_attempt(
                returncode=0,
                output="",
                checkpoint_path=checkpoint,
                device="cuda",
            )

            self.assertEqual(result.status, "cuda_fault")
            self.assertEqual(result.failed, 1)

    def test_classify_attempt_detects_partial_cuda_fault(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            checkpoint = base / "embed_checkpoint_part001.cuda.json"
            failed_log = checkpoint.with_name(f"{checkpoint.stem}_failed.jsonl")
            checkpoint.write_text(
                '{"status":"completed","counters":{"queued":4,"succeeded":2,"failed":2}}',
                encoding="utf-8",
            )
            failed_log.write_text(
                '{"path":"a.mp3","error":"AcceleratorError(\\"CUDA error: an illegal memory access was encountered\\")"}\n'
                '{"path":"b.mp3","error":"AcceleratorError(\\"CUDA error: an illegal memory access was encountered\\")"}\n',
                encoding="utf-8",
            )

            result = run_embed_chunks._classify_attempt(
                returncode=0,
                output="",
                checkpoint_path=checkpoint,
                device="cuda",
            )

            self.assertEqual(result.status, "cuda_fault_partial")
            self.assertEqual(result.succeeded, 2)
            self.assertEqual(result.failed, 2)

    def test_process_chunk_splits_cuda_faulted_chunk_and_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            chunk_path = base / "part001.txt"
            chunk_path.write_text("a.mp3\nb.mp3\nc.mp3\nd.mp3\n", encoding="utf-8")
            checkpoint_dir = base / "checkpoints"
            checkpoint_dir.mkdir()

            attempts: list[tuple[str, str]] = []

            def fake_run_chunk_attempt(**kwargs):
                attempts.append((kwargs["chunk_path"].name, kwargs["device"]))
                checkpoint_path = kwargs["checkpoint_path"]
                if kwargs["chunk_path"].name == "part001.txt":
                    return _result(
                        run_embed_chunks,
                        status="cuda_fault",
                        device="cuda",
                        checkpoint_path=checkpoint_path,
                        failed=4,
                    )
                return _result(
                    run_embed_chunks,
                    status="ok",
                    device=kwargs["device"],
                    checkpoint_path=checkpoint_path,
                    succeeded=2,
                )

            stats: dict[str, int] = {}
            with mock.patch.object(run_embed_chunks, "_run_chunk_attempt", side_effect=fake_run_chunk_attempt):
                rc = run_embed_chunks._process_chunk(
                    repo=base,
                    chunk_path=chunk_path,
                    checkpoint_dir=checkpoint_dir,
                    checkpoint_every=25,
                    num_workers=4,
                    batch_size=4,
                    device="cuda",
                    min_chunk_size=2,
                    max_split_depth=2,
                    disable_cpu_fallback=False,
                    dry_run=False,
                    stats=stats,
                )

            self.assertEqual(rc, 0)
            self.assertEqual(stats["cuda_fault_chunks"], 1)
            self.assertEqual(stats["split_retries"], 1)
            self.assertEqual(stats["ok_chunks"], 2)
            self.assertEqual(attempts[0], ("part001.txt", "cuda"))
            self.assertIn(("part001.d1a.txt", "cuda"), attempts)
            self.assertIn(("part001.d1b.txt", "cuda"), attempts)

    def test_process_chunk_falls_back_to_cpu_for_small_cuda_faulted_chunk(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            chunk_path = base / "part002.txt"
            chunk_path.write_text("a.mp3\nb.mp3\n", encoding="utf-8")
            checkpoint_dir = base / "checkpoints"
            checkpoint_dir.mkdir()

            attempts: list[tuple[str, str]] = []

            def fake_run_chunk_attempt(**kwargs):
                attempts.append((kwargs["chunk_path"].name, kwargs["device"]))
                checkpoint_path = kwargs["checkpoint_path"]
                if kwargs["device"] == "cuda":
                    return _result(
                        run_embed_chunks,
                        status="cuda_fault",
                        device="cuda",
                        checkpoint_path=checkpoint_path,
                        failed=2,
                    )
                return _result(
                    run_embed_chunks,
                    status="ok",
                    device="cpu",
                    checkpoint_path=checkpoint_path,
                    succeeded=2,
                )

            stats: dict[str, int] = {}
            with mock.patch.object(run_embed_chunks, "_run_chunk_attempt", side_effect=fake_run_chunk_attempt):
                rc = run_embed_chunks._process_chunk(
                    repo=base,
                    chunk_path=chunk_path,
                    checkpoint_dir=checkpoint_dir,
                    checkpoint_every=25,
                    num_workers=4,
                    batch_size=4,
                    device="cuda",
                    min_chunk_size=10,
                    max_split_depth=1,
                    disable_cpu_fallback=False,
                    dry_run=False,
                    stats=stats,
                )

            self.assertEqual(rc, 0)
            self.assertEqual(stats["cuda_fault_chunks"], 1)
            self.assertEqual(stats["cpu_fallback_attempts"], 1)
            self.assertEqual(stats["cpu_fallback_recovered"], 1)
            self.assertEqual(attempts, [("part002.txt", "cuda"), ("part002.txt", "cpu")])

    def test_process_chunk_retries_failed_subset_for_partial_cuda_fault(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            chunk_path = base / "part003.txt"
            chunk_path.write_text("a.mp3\nb.mp3\nc.mp3\nd.mp3\n", encoding="utf-8")
            checkpoint_dir = base / "checkpoints"
            checkpoint_dir.mkdir()
            failed_log = checkpoint_dir / "embed_checkpoint_part003.cuda_failed.jsonl"
            failed_log.write_text(
                '{"path":"c.mp3","error":"AcceleratorError(\\"CUDA error\\")"}\n'
                '{"path":"d.mp3","error":"AcceleratorError(\\"CUDA error\\")"}\n',
                encoding="utf-8",
            )

            attempts: list[tuple[str, str, list[str]]] = []

            def fake_run_chunk_attempt(**kwargs):
                chunk_paths = run_embed_chunks._read_chunk_paths(kwargs["chunk_path"])
                attempts.append((kwargs["chunk_path"].name, kwargs["device"], chunk_paths))
                checkpoint_path = kwargs["checkpoint_path"]
                if kwargs["chunk_path"].name == "part003.txt":
                    return run_embed_chunks.ChunkAttemptResult(
                        status="cuda_fault_partial",
                        returncode=0,
                        checkpoint_path=checkpoint_path,
                        failed_log_path=failed_log,
                        checkpoint={},
                        error_counts={"AcceleratorError('CUDA error')": 2},
                        queued=4,
                        succeeded=2,
                        failed=2,
                        output="",
                        device="cuda",
                    )
                return _result(
                    run_embed_chunks,
                    status="ok",
                    device=kwargs["device"],
                    checkpoint_path=checkpoint_path,
                    succeeded=len(chunk_paths),
                )

            stats: dict[str, int] = {}
            with mock.patch.object(run_embed_chunks, "_run_chunk_attempt", side_effect=fake_run_chunk_attempt):
                rc = run_embed_chunks._process_chunk(
                    repo=base,
                    chunk_path=chunk_path,
                    checkpoint_dir=checkpoint_dir,
                    checkpoint_every=25,
                    num_workers=4,
                    batch_size=4,
                    device="cuda",
                    min_chunk_size=10,
                    max_split_depth=1,
                    disable_cpu_fallback=False,
                    dry_run=False,
                    stats=stats,
                )

            self.assertEqual(rc, 0)
            self.assertEqual(stats["partial_cuda_chunks"], 1)
            self.assertEqual(stats["failed_subset_retries"], 1)
            self.assertEqual(stats["cpu_fallback_attempts"], 1)
            self.assertEqual(stats["cpu_fallback_recovered"], 1)
            self.assertEqual(attempts[0][0], "part003.txt")
            self.assertEqual(attempts[1][2], ["c.mp3", "d.mp3"])


if __name__ == "__main__":
    unittest.main()
