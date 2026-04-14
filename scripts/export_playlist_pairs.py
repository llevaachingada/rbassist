from __future__ import annotations

import argparse
import json
import pathlib

from rbassist.playlist_pairs import build_playlist_pair_dataset, load_playlists_for_dataset, write_pair_dataset_jsonl
from rbassist.utils import load_meta


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export read-only playlist pair labels for future learned similarity training."
    )
    parser.add_argument("--source", choices=["db", "xml"], default="db", help="Playlist source.")
    parser.add_argument("--xml-path", default=None, help="Rekordbox XML path when --source xml is used.")
    parser.add_argument("--playlist", action="append", default=[], help="Playlist path/name to export. Repeatable.")
    parser.add_argument("--out", default="data/training/playlist_pairs.jsonl", help="Output JSONL dataset path.")
    parser.add_argument("--summary", default="", help="Optional JSON summary path.")
    parser.add_argument("--max-playlists", type=int, default=None, help="Maximum playlists to export when auto-discovering.")
    parser.add_argument("--max-same-playlist-pairs", type=int, default=500, help="Cap positive pairs per playlist.")
    parser.add_argument("--negatives-per-positive", type=float, default=1.0, help="Different-playlist negatives per positive.")
    parser.add_argument("--seed", type=int, default=13, help="Random seed for deterministic sampling.")
    parser.add_argument("--no-weak-positives", action="store_true", help="Only emit adjacent same-playlist positives.")
    parser.add_argument("--dry-run", action="store_true", help="Print counts without writing the dataset.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    playlists = load_playlists_for_dataset(
        source=args.source,
        playlist_refs=args.playlist,
        xml_path=args.xml_path,
        max_playlists=args.max_playlists,
    )
    meta_tracks = load_meta().get("tracks", {})
    result = build_playlist_pair_dataset(
        playlists,
        meta_tracks=meta_tracks,
        include_weak_positives=not args.no_weak_positives,
        negatives_per_positive=args.negatives_per_positive,
        max_pairs_per_playlist=args.max_same_playlist_pairs,
        random_seed=args.seed,
    )
    payload = {"diagnostics": result.diagnostics, "out": str(pathlib.Path(args.out))}
    if not args.dry_run:
        out_path = write_pair_dataset_jsonl(result.rows, args.out)
        payload["out"] = str(out_path)
    if args.summary:
        summary_path = pathlib.Path(args.summary)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
