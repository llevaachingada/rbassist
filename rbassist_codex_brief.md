# rbassist – Codex / Copilot Optimization Brief

> Use this file as the prompt for VS Code Copilot / Chat while you are on a feature branch, e.g. `feat/ai-full-claude-pass`.

You are working on the **rbassist** project in this workspace.

## Context

- Current branch: a feature branch based off `origin/main`, for example: `feat/ai-full-claude-pass`.
- **rbassist** is a Windows-first, GPU-accelerated Rekordbox assistant toolchain (Typer CLI + Streamlit GUI).
- Target machine: **Windows 11**, **32 GB RAM**, **RTX 4060 (8 GB VRAM)**, fast NVMe SSD.
- Target library size: **tens of thousands of tracks**, so performance and I/O patterns matter.

You are implementing and expanding on a static analysis report that suggested debugging fixes, performance improvements, and feature additions. Some parts of that report overstated severity (for example, calling a type-hint inconsistency a critical crash), so **do not blindly trust that report**. Use the **actual code in this repo** as the source of truth.

### Global rules

- Keep existing **CLI commands and flags backwards-compatible**.
- Do **not** break `rbassist` CLI or webapp behavior.
- Work in **small, logical commits**, and show me diffs after each cluster of changes.
- Prefer clear, well-named helpers over giant refactors.
- Keep code style consistent with the existing codebase.

---

## A) Debug / Cleanup Fixes

### A1) `analyze.py` – TaskID annotation fix

- File: `rbassist/analyze.py`
- There is a variable annotated like `task_id: TaskID | None = None` but `TaskID` is not imported.
- Because the file uses `from __future__ import annotations`, this is not a runtime crash, but it is a typing inconsistency.

**Task:**

- Fix this by importing `TaskID` from `rich.progress`:

  ```python
  from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, TaskID
  ```

  **or**, if that proves awkward, change the annotation to `int | None` and add a brief comment explaining that Rich uses integer task IDs.

- Do **not** change the runtime behavior – this is purely about type clarity.

---

### A2) `cli.py` – unify `analyze_bpm_key`, remove inline legacy version

- File: `rbassist/cli.py`
- There is an older inline implementation of `analyze_bpm_key` and a newer implementation in `rbassist/analyze.py`. The CLI currently does a try/except fallback to the inline version if import fails.

**Task:**

- Remove the **inline** `analyze_bpm_key` implementation and the import-fallback logic.
- Always import from `.analyze`:

  ```python
  from .analyze import analyze_bpm_key
  ```

- Ensure the `rbassist analyze` command still passes the same parameters (`paths`, `duration_s`, `only_new`, `force`, `add_cues`, etc.) to this function.
- Do **not** change the CLI signature or user-visible options.

---

### A3) `embed.py` – robust progress stopping

- File: `rbassist/embed.py`
- `build_embeddings` creates a Rich `Progress` instance when `progress_callback` is `None`. It calls `progress.stop()` at the end, but a top-level exception could still potentially leave the bar in a weird state.

**Task:**

- Wrap the core body of `build_embeddings` in a `try/finally` block so that `progress.stop()` is always called if a `Progress` object exists, even if an unexpected exception bubbles out.
- Do **not** change the per-file exception behavior or the parallel I/O design; just harden the progress handling.

---

### A4) Repo hygiene – remove stray editor artifact(s), update `.gitignore`

- There is at least one stray file like `rbassist/got canvas 92325.txt` (an editor/canvas scratch).

**Task:**

- Remove such files from the repo.
- Add an appropriate pattern to `.gitignore` to keep them out in future (for example, `*canvas*.txt` if that’s safe after inspecting filenames).

After A-level changes, **show me the git diff** for review.

---

## B) Performance: Embedding & Analysis (RTX 4060 + 32 GB tuning)

### B1) `embed.py` – GPU-aware batching for model inference

Goal: keep the existing **parallel I/O** but stop doing strictly *one-track-at-a-time* model inference. Introduce batching tuned for an RTX 4060 (8 GB VRAM) with durations of ~60–120 seconds.

- File: `rbassist/embed.py`
- Today: ThreadPoolExecutor parallelizes I/O, but model inference uses a single `MertEmbedder` instance and is strictly serial.

**Task:**

- In `build_embeddings`, once audio arrays are decoded, group them into **batches** (e.g., 4–8 tracks per batch).
- Add a CLI/config parameter for batch size, e.g. `batch_size: int = 1`, and expose it in the embed CLI as `--batch-size`:
  - GPU: default `batch_size ≈ 4` (safe for RTX 4060).
  - CPU: default `batch_size = 1` (no change).
- Implement batching like this:
  - Accumulate `(path, audio_array, sr, ...)` triples into a batch.
  - When the batch is full **or** you’re at the end, call the embedding model once on the batch via the existing MERT embedder.
  - Save one embedding per track, mapping batch outputs back to paths.
- Maintain existing logging/progress behavior, but tick progress **per track** in the batch.
- Do **not** blow VRAM – keep defaults conservative and put aggressive settings in docs/README.

---

### B2) `utils.file_sig` – fast signatures for re-analysis

- File: likely `rbassist/utils.py` (where `file_sig` lives).
- Current: `file_sig(path)` does a **full SHA1** over the file contents.

**Task:**

- Add a “fast signature” helper without changing default behavior yet:

  ```python
  def file_sig_fast(path: str) -> str:
      """Fast, non-cryptographic file signature based on mtime and size."""
      st = os.stat(path)
      return f"{st.st_mtime_ns}_{st.st_size}"
  ```

- Add a comment near `file_sig` explaining:
  - Full SHA1 is accurate but slow for big libraries.
  - `file_sig_fast` is a cheap proxy for large libraries.
- Optionally centralize signature selection in a single helper (e.g. `current_file_sig(path)`) that calls `file_sig` for now, but is easy to switch to `file_sig_fast` later.
- Do **not** change semantics yet – we’re wiring in the option and documenting it.

---

### B3) Meta write behavior – basic batching (no DB migration)

- `save_meta()` currently rewrites the entire JSON on each call, which becomes expensive for large `meta.json`.

**Task:**

- Introduce a simple batching pattern **without** migrating to SQLite/LMDB:
  - Add a small “meta manager” helper or context manager that:
    - Tracks whether `meta` has changed.
    - Allows multiple in-memory updates.
    - Writes to disk only when:
      - A context exits, or
      - `flush_meta()` is explicitly called.
- Use this in the most write-heavy paths (e.g., `tags-auto --apply`, analysis loops) so `save_meta(meta)` is called **once per command**, not hundreds of times.
- Keep the on-disk format the same: a single JSON file.

---

### B4) `analyze.py` – optional parallel BPM/Key analysis

- File: `rbassist/analyze.py`
- Current: `analyze_bpm_key` runs serially.

**Task:**

- Extend or wrap `analyze_bpm_key` to support an optional `workers: int | None = None` parameter.
  - `workers is None` → keep current serial behavior.
  - `workers > 1` → use `concurrent.futures.ProcessPoolExecutor` for the CPU-heavy parts (librosa BPM/key estimation).
- Extract the per-file work into a helper like `_analyze_single(...)` that returns the updated info for one path.
- In the parent process:
  - Dispatch tasks to workers.
  - Merge results back into `meta`.
  - Update progress as tasks complete.
- For now, do **not** change default CLI behavior; just wire the option and document recommended worker counts for fast machines.

Prioritize B1 and B2 first, then B3 and B4.

---

## C) Performance: Indexing & Recommendations

### C1) HNSW index caching in webapp

- File: `rbassist/webapp.py`
- Currently: a fresh HNSW index is constructed and loaded from disk on every recommendation query.

**Task:**

- Implement a cached loader using Streamlit’s `@st.cache_resource` (or the modern equivalent):

  ```python
  @st.cache_resource
  def load_hnsw_index(dim: int):
      index = hnswlib.Index(space="cosine", dim=dim)
      index.load_index(str(IDX / "hnsw.idx"))
      index.set_ef(64)
      return index
  ```

- Modify the k-NN helper to call `load_hnsw_index(vec.shape[0])` instead of constructing/loading a fresh index per call.
- Do **not** change how `analyze_bpm_key` is called from the webapp.

---

### C2) Incremental HNSW index building

- Files: the module(s) implementing `rbassist index` and HNSW index creation.
- Current: `rbassist index` rebuilds the entire index from scratch.

**Task:**

- Add an **incremental** index mode that:
  - Loads existing index and path mapping (if present).
  - Scans embedding files on disk.
  - Determines:
    - New embeddings not in the mapping.
    - Optionally, missing/deleted tracks.
  - Adds new items to the existing index with appropriate labels.
  - Saves updated index and mapping.
- CLI behavior:
  - Default `rbassist index` can remain as a full rebuild.
  - Add a flag like `--incremental` to use the incremental code path.
- Ensure label → path mapping stays consistent and is stored on disk (JSON or simple text).

---

### C3) Safer embedding loading for index building

**Task:**

- Introduce a helper, e.g. `load_embedding_safe(path: str) -> np.ndarray | None` that:
  - Calls `np.load`.
  - Verifies shape matches expected embedding dimension.
  - Catches exceptions and logs clear warnings for corrupted or wrong-shaped arrays, returning `None` instead of hard-failing.
- Use this helper wherever embeddings are loaded for index building.

---

## D) Model / Cache Behavior & Storage Optimizations

### D1) Model cache behavior

- In `embed.py` (or wherever the MERT model is loaded via `transformers`):

**Task:**

- Confirm we rely on standard Hugging Face caching.
- Optionally set or document an explicit cache dir:

  ```python
  os.environ.setdefault(
      "HF_HOME",
      str(pathlib.Path.home() / ".cache" / "huggingface")
  )
  ```

- Add a short README note about cache location and approximate model size.

---

### D2) Embedding storage as float16

**Task:**

- When **saving** embeddings to disk:
  - Convert to float16:

    ```python
    vec_fp16 = vec.astype(np.float16)
    np.save(path, vec_fp16)
    ```

- When **loading** for index/recommendation:
  - Convert back to float32 in memory:

    ```python
    vec = np.load(path).astype(np.float32)
    ```

- Ensure all index-building and recommendation code expects float32 at runtime.
- This roughly halves on-disk size and lowers RAM pressure for large libraries.

---

## E) New Features / Experimental Capabilities

### E1) Duplicate detection improvements

- There is already near-duplicate detection using embedding distance.

**Task:**

- Add an **exact** duplicate mode using a fast content hash (e.g., SHA1 of the full file or a smaller hash over a limited portion of the audio).
- Integrate this into the duplicates CLI as an optional flag (`--exact` / `--content-hash`).
- Do **not** pull in heavy external fingerprinting libraries in this pass; a basic hash is sufficient.

---

### E2) Batch / sequence recommendation API

**Task:**

- Add an internal helper (and optionally experimental CLI) that, given multiple seed tracks, suggests a sequence/set.
- First iteration can be simple:
  - Compute a combined seed embedding (e.g., mean of seed vectors).
  - Use the existing HNSW index to find close neighbors.
  - Apply simple rules to avoid repeats and encourage smooth transitions.
- Expose as either:
  - Experimental CLI command (e.g. `rbassist recommend-sequence`), or
  - A helper function that the webapp can hook into later.

---

### E3) Weight-tuning scaffold (A/B experiments)

**Task:**

- Add a clearly marked “experimental” module, e.g. `rbassist/experiments/weights.py`, containing a stub like:

  ```python
  def optimize_weights(ground_truth_pairs, initial_weights=None):
      """
      Stub for future weight optimization (e.g. using scipy.optimize).
      Does not affect production behavior yet.
      """
      ...
  ```

- No need to fully implement complicated optimization yet; the goal is to have a clear, isolated place for it.

---

## F) Testing & Validation

### F1) Expand pytest coverage

**Task:**

- Add or extend tests (in `tests/`) for:
  - `embed.py` – float16 save/load, basic embed workflow on synthetic data.
  - `analyze.py` – fast smoke tests for BPM/key on tiny fixtures.
  - Index/recommend code – small synthetic embeddings to test index building, incremental indexing, and `load_embedding_safe`.
- Keep tests small and fast; use synthetic data instead of real audio when possible.

---

### F2) Sanity checks for large-library settings

**Task:**

- Add a small test or script that simulates a few thousand fake embeddings and builds an index, to verify:
  - Memory remains reasonable on a 32 GB machine.
  - Incremental indexing works.
  - Webapp’s HNSW caching does not crash.

---

## After Making These Changes

1. Show me the **git diff** in logical chunks after:
   - A) debug/cleanup
   - B) embed/analyze performance
   - C) index/recommend performance
   - D/E) storage + new features / experiments
2. Run:
   - `python -m compileall rbassist`
   - `pytest`
3. Do **not** push to `origin` automatically; I will review locally and push myself.
