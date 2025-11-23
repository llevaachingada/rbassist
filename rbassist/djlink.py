from __future__ import annotations
# Optional: pip install git+https://github.com/flesniak/python-prodj-link.git
import time
from rich.console import Console
console = Console()
try:
    from prodjlink import ProDJLink
except Exception as e:
    raise RuntimeError("python-prodj-link not installed.") from e

def run():
    link = ProDJLink(); link.start()
    console.print("[green]Listening for Pro DJ Link devices... (Ctrl+C to stop)")
    try:
        while True:
            for pid, player in link.players.items():
                if not player.online: continue
                state = player.state
                title = getattr(state, 'title', '')
                artist = getattr(state, 'artist', '')
                bpm = getattr(state, 'tempo', None)
                console.print(f"Deck {pid}: {artist} - {title} | BPM={bpm}")
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        link.stop()