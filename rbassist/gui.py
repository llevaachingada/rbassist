from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    """
    Launch the Streamlit web UI instead of the legacy Tkinter window.

    The old Tk wrapper caused focus/grabbing issues for a lot of users; by
    bouncing directly to Streamlit we keep everything in the browser and avoid
    Tk dependency headaches.
    """
    try:
        import streamlit  # type: ignore  # noqa: F401
    except Exception:
        sys.stderr.write(
            "Streamlit is not installed. Install rbassist[web] or run:\n"
            "  pip install streamlit streamlit-modal\n"
        )
        sys.exit(1)

    webapp = Path(__file__).resolve().parent / "webapp.py"
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(webapp)],
        check=False,
    )


if __name__ == "__main__":
    main()
