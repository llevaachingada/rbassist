from __future__ import annotations
import typer, pathlib
from typing import Optional
from rich import print
from .utils import console, walk_audio, load_meta, save_meta
from .embed import build_embeddings
from .recommend import build_index, recommend
from .bandcamp import import_bandcamp

app = typer.Typer(help="Rekordbox Assist (starter)")

@app.command("embed-build")
def embed_build(
    path: str = typer.Argument(..., help="Folder or file (audio)"),
    model: str = typer.Option("m-a-p/MERT-v1-330M", help="HF model"),
    duration: int = typer.Option(120, help="Seconds to embed (0=full)"),
):
    files = walk_audio([path])
    build_embeddings(files, model_name=model, duration_s=duration)
    console.print("[green]Embeddings built.")


@app.command("index")
def index():
    build_index()


@app.command("recommend")
def cmd_recommend(
    seed: str = typer.Argument(..., help="Seed path or 'Artist - Title' substring"),
    top: int = 25,
):
    recommend(seed, top=top)


@app.command("import-tags")
def cmd_import_tags(csv_path: str, config: str = "config/tags.yml"):
    meta = load_meta()
    meta = import_bandcamp(csv_path, config, meta)
    save_meta(meta)
    console.print("[green]Imported Bandcamp tags into local meta (for filtering/notes).\n[bold yellow]Note:[/] Writing My Tags into Rekordbox DB is a separate step.")


if __name__ == "__main__":
    app()