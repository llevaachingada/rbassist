"""
CLI commands for AI tag learning system.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from . import safe_tagstore, active_learning, user_model
from .tag_model import learn_tag_profiles
from .utils import load_meta

app = typer.Typer(help="AI-powered tag learning commands")
console = Console()


@app.command()
def migrate():
    """Migrate tags from old tagstore system to new safe namespace system."""
    console.print("[yellow]Starting migration from old tag system...")
    result = safe_tagstore.migrate_from_old_tagstore()

    if result["tracks_migrated"] > 0:
        console.print(
            f"[green]✓ Successfully migrated {result['tracks_migrated']} tracks "
            f"with {result['tags_migrated']} total tags"
        )
        console.print("[green]✓ All tags are now in the USER namespace (protected)")
    else:
        console.print("[yellow]No tags to migrate")


@app.command()
def stats():
    """Show statistics about tags and AI suggestions."""
    # User tags
    user_tags = safe_tagstore.load_user_tags()
    all_user_tags = safe_tagstore.get_all_user_tags()

    # AI suggestions
    suggestion_stats = safe_tagstore.get_suggestion_stats()

    # Corrections
    correction_stats = safe_tagstore.get_correction_stats()

    # User model
    user_style = user_model.UserTaggingStyle.load()
    accuracy_stats = user_style.get_correction_accuracy()
    most_used = user_style.get_most_used_tags(top_k=10)

    # Display
    table = Table(title="AI Tag Learning Stats")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("User Tagged Tracks", str(len(user_tags)))
    table.add_row("Unique User Tags", str(len(all_user_tags)))
    table.add_row(
        "Tracks with AI Suggestions", str(suggestion_stats["tracks_with_suggestions"])
    )
    table.add_row("Total AI Suggestions", str(suggestion_stats["total_suggestions"]))
    table.add_row("Suggestions Accepted", str(correction_stats["accepted"]))
    table.add_row("Suggestions Rejected", str(correction_stats["rejected"]))
    table.add_row(
        "AI Acceptance Rate", f"{accuracy_stats['acceptance_rate']:.1%}"
    )

    console.print(table)

    if most_used:
        console.print("\n[cyan]Your Most Used Tags:")
        for i, (tag, count) in enumerate(most_used, 1):
            console.print(f"  {i}. {tag} ({count} times)")


@app.command()
def learn(
    min_samples: int = typer.Option(
        3, help="Minimum number of examples needed per tag"
    ),
    margin: float = typer.Option(
        0.0, help="Confidence margin for accepting suggestions"
    ),
):
    """
    Learn tag profiles from user tags and generate AI suggestions.
    """
    console.print("[cyan]Learning tag profiles from your tags...")

    meta = load_meta()
    profiles = learn_tag_profiles(min_samples=min_samples, meta=meta)

    if not profiles:
        console.print(
            "[red]No tags to learn from! Tag some tracks first.", style="bold"
        )
        return

    console.print(f"[green]✓ Learned {len(profiles)} tag profiles")

    # Show profile details
    table = Table(title="Learned Tag Profiles")
    table.add_column("Tag", style="cyan")
    table.add_column("Samples", style="yellow")
    table.add_column("Mean Similarity", style="green")
    table.add_column("Threshold", style="magenta")

    for tag, profile in profiles.items():
        table.add_row(
            tag,
            str(profile.samples),
            f"{profile.mean_sim:.3f}",
            f"{profile.threshold:.3f}",
        )

    console.print(table)

    # Find untagged tracks
    user_tags = safe_tagstore.load_user_tags()
    untagged_tracks = [
        p
        for p, info in meta.get("tracks", {}).items()
        if info.get("embedding") and p not in user_tags
    ]

    if not untagged_tracks:
        console.print("[yellow]No untagged tracks with embeddings found")
        return

    console.print(f"\n[cyan]Generating suggestions for {len(untagged_tracks)} tracks...")

    from .tag_model import suggest_tags_for_tracks

    suggestions = suggest_tags_for_tracks(
        untagged_tracks, profiles, margin=margin, top_k=3, meta=meta
    )

    if not suggestions:
        console.print("[yellow]No suggestions met confidence thresholds")
        return

    # Load user model to adjust suggestions
    user_style = user_model.UserTaggingStyle.load()

    # Store in AI suggestions
    suggestion_count = 0
    for track, tag_list in suggestions.items():
        track_suggestions = {tag: score for tag, score, _ in tag_list}

        # Adjust based on user preferences
        adjusted = user_style.adjust_ai_suggestions(track_suggestions)

        # Filter to tags user actually uses
        filtered = {
            tag: conf
            for tag, conf in adjusted.items()
            if user_style.should_suggest_tag(tag, min_usage=2)
        }

        if filtered:
            for tag, conf in filtered.items():
                safe_tagstore.add_ai_suggestion(track, tag, conf)
            suggestion_count += 1

    console.print(
        f"[green]✓ Generated suggestions for {suggestion_count} tracks"
    )
    console.print("[cyan]Use 'rbassist ai-tag review' to review and accept/reject")


@app.command()
def review(
    min_confidence: float = typer.Option(
        0.5, help="Minimum confidence to show suggestions"
    ),
    limit: int = typer.Option(20, help="Maximum number of tracks to show"),
):
    """
    Review AI tag suggestions interactively.
    """
    suggestions = safe_tagstore.get_all_ai_suggestions(min_confidence=min_confidence)

    if not suggestions:
        console.print("[yellow]No AI suggestions found. Run 'learn' first.")
        return

    console.print(
        f"[cyan]Reviewing suggestions (showing up to {limit} tracks)...\n"
    )

    import pathlib

    for i, (track, tag_scores) in enumerate(list(suggestions.items())[:limit], 1):
        track_name = pathlib.Path(track).name
        console.print(f"[bold cyan]{i}. {track_name}[/bold cyan]")

        for tag, confidence in sorted(
            tag_scores.items(), key=lambda x: x[1], reverse=True
        ):
            console.print(f"   {tag}: {confidence:.0%}")

        console.print()

    console.print(
        f"[green]Use the UI (rbassist-ui) for interactive review and acceptance"
    )


@app.command()
def uncertain(
    strategy: str = typer.Option(
        "margin",
        help="Uncertainty strategy: margin, entropy, or least_confidence",
    ),
    top_k: int = typer.Option(10, help="Number of uncertain tracks to show"),
):
    """
    Find tracks where AI is most uncertain - these teach the AI the most.
    """
    import numpy as np

    console.print(f"[cyan]Finding uncertain tracks using {strategy} strategy...")

    meta = load_meta()
    profiles = learn_tag_profiles(min_samples=3, meta=meta)

    if not profiles:
        console.print("[red]No profiles learned yet. Run 'learn' first.")
        return

    # Get untagged tracks with embeddings
    user_tags = safe_tagstore.load_user_tags()
    untagged_embeddings = {}

    for path, info in meta.get("tracks", {}).items():
        if path not in user_tags and info.get("embedding"):
            try:
                emb = np.load(info["embedding"])
                if emb.ndim != 1:
                    emb = emb.reshape(-1)
                untagged_embeddings[path] = emb
            except Exception:
                continue

    if not untagged_embeddings:
        console.print("[yellow]No untagged tracks with embeddings")
        return

    # Get uncertain tracks
    uncertain_tracks = active_learning.suggest_tracks_to_tag(
        untagged_embeddings, profiles, strategy=strategy, top_k=top_k
    )

    if not uncertain_tracks:
        console.print("[yellow]No uncertain tracks found")
        return

    console.print(
        f"\n[green]Found {len(uncertain_tracks)} uncertain tracks:\n"
    )

    import pathlib

    for i, track_info in enumerate(uncertain_tracks, 1):
        track_name = pathlib.Path(track_info.path).name
        explanation = active_learning.explain_uncertainty(track_info)

        console.print(f"[bold cyan]{i}. {track_name}[/bold cyan]")
        console.print(f"   {explanation}")
        console.print(
            f"   Uncertainty: {track_info.uncertainty_score:.3f}"
        )
        console.print()


@app.command()
def sync_user_model():
    """Sync user learning model from tags and corrections."""
    console.print("[cyan]Syncing user learning model...")

    user_tags = safe_tagstore.load_user_tags()
    user_style = user_model.sync_user_model_from_tags(user_tags)

    correction_log = safe_tagstore.load_correction_history()
    user_style = user_model.sync_user_model_from_corrections(correction_log)

    stats = user_style.get_correction_accuracy()

    console.print(f"[green]✓ Synced user model")
    console.print(f"   Total corrections: {stats['total_corrections']}")
    console.print(f"   Acceptance rate: {stats['acceptance_rate']:.1%}")

    if stats["most_corrected_tags"]:
        console.print("\n[yellow]Most corrected tags:")
        for tag, count in stats["most_corrected_tags"][:5]:
            console.print(f"   {tag}: {count} corrections")


@app.command()
def validate():
    """Validate tag safety - check for conflicts."""
    console.print("[cyan]Running safety validation...")

    issues = safe_tagstore.validate_tag_safety()

    if not issues:
        console.print("[green]✓ All safety checks passed!")
    else:
        console.print(f"[red]⚠ Found {len(issues)} issues:")
        for issue in issues:
            console.print(f"  - {issue}")


@app.command()
def clear_suggestions(
    confirm: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompt"
    ),
):
    """Clear all AI suggestions."""
    if not confirm:
        response = typer.confirm("Clear all AI suggestions?")
        if not response:
            console.print("[yellow]Cancelled")
            return

    count = safe_tagstore.clear_all_ai_suggestions()
    console.print(f"[green]✓ Cleared {count} suggestions")


if __name__ == "__main__":
    app()
