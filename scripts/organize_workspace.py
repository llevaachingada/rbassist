#!/usr/bin/env python3
"""Organize a messy RB Assist workspace folder.

This helper is intentionally conservative: it scans only the top level of a
folder (no recursion) and suggests moves for common RB Assist artifacts so your
music files stay untouched. By default it performs a dry run; pass ``--apply``
to actually move files into the suggested subfolders.
"""
from __future__ import annotations

import argparse
import fnmatch
import pathlib
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class Rule:
    dest: str
    patterns: Tuple[str, ...]
    description: str


RULES: List[Rule] = [
    Rule("exports", ("rbassist.xml", "*.xml"), "Export files from Rekordbox/RB Assist"),
    Rule("archives", ("*.zip", "*.7z", "*.rar", "*.tar", "*.tar.gz", "*.tgz"), "Compressed archives"),
    Rule("scripts", ("*.ps1", "*.bat", "*.cmd", "*.sh"), "Helper scripts and installers"),
    Rule("shortcuts", ("*.lnk",), "Windows shortcuts"),
    Rule("notes", ("*.txt", "*.md", "*.log"), "Notes and scratch files"),
    Rule("temp", ("TEMP_*", "temp_*", "*.tmp"), "Temporary files"),
]


@dataclass
class PlanItem:
    source: pathlib.Path
    dest: pathlib.Path
    rule: Rule


def classify(path: pathlib.Path) -> Optional[Rule]:
    name = path.name
    for rule in RULES:
        if any(fnmatch.fnmatch(name, pattern) for pattern in rule.patterns):
            return rule
    return None


def build_plan(root: pathlib.Path) -> List[PlanItem]:
    plan: List[PlanItem] = []
    for child in root.iterdir():
        if not child.is_file():
            continue
        rule = classify(child)
        if rule is None:
            continue
        dest_dir = root / rule.dest
        plan.append(PlanItem(source=child, dest=dest_dir / child.name, rule=rule))
    return plan


def apply_plan(plan: Iterable[PlanItem]) -> None:
    for item in plan:
        item.dest.parent.mkdir(parents=True, exist_ok=True)
        item.source.replace(item.dest)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Organize RB Assist workspace clutter.")
    parser.add_argument(
        "path",
        nargs="?",
        type=pathlib.Path,
        default=pathlib.Path("."),
        help="Workspace folder to organize (defaults to current directory).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform the moves. Without this flag, a dry run is shown.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.path.expanduser().resolve()

    if not root.exists():
        print(f"[error] Workspace '{root}' does not exist.")
        return 1
    if not root.is_dir():
        print(f"[error] Workspace '{root}' is not a directory.")
        return 1

    plan = build_plan(root)
    if not plan:
        print(f"No matching files found to organize in '{root}'.")
        return 0

    print(f"Planned moves in '{root}':")
    for item in plan:
        print(f"  {item.source.name} -> {item.rule.dest}  ({item.rule.description})")

    if args.apply:
        apply_plan(plan)
        print("\nApplied.")
    else:
        print("\nDry run only. Re-run with --apply to move files.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
