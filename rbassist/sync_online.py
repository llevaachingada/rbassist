from __future__ import annotations
import csv
from .utils import load_meta


def match_local(artist: str, title: str) -> list[str]:
    artist = (artist or "").lower().strip()
    title = (title or "").lower().strip()
    hits: list[str] = []
    meta = load_meta().get("tracks", {})
    for path, info in meta.items():
        a = (info.get("artist", "") or "").lower()
        t = (info.get("title", "") or "").lower()
        if artist in a and title in t:
            hits.append(path)
    return hits


def import_csv_playlist(csv_path: str, artist_col: str = "artist", title_col: str = "title") -> list[str]:
    rows = list(csv.DictReader(open(csv_path, newline="", encoding="utf-8")))
    matched: list[str] = []
    for r in rows:
        a, t = r.get(artist_col, ""), r.get(title_col, "")
        matched.extend(match_local(a, t))
    # De-dup preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for p in matched:
        if p not in seen:
            uniq.append(p)
            seen.add(p)
    return uniq


def spotify_playlist_tracks(playlist_url: str) -> list[tuple[str, str]]:
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
    except Exception as e:
        raise RuntimeError("Install spotipy to use Spotify syncing: pip install spotipy") from e
    scope = "playlist-read-private"
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope))
    pid = playlist_url.split("/")[-1].split("?")[0]
    out: list[tuple[str, str]] = []
    results = sp.playlist_items(pid)
    while results:
        for it in results.get("items", []):
            track = it.get("track") or {}
            name = track.get("name", "")
            artists = ", ".join([a.get("name", "") for a in (track.get("artists") or [])])
            out.append((artists, name))
        results = sp.next(results) if results.get("next") else None
    return out

