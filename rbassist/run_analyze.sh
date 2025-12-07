
#!/usr/bin/env bash
set -e
if [ ! -x ".venv/bin/python" ]; then
  echo "[!] .venv not found. Run: python install.py"
  exit 1
fi
read -r -p "Enter path to your music folder [/Volumes/Music]: " MUSIC
MUSIC=${MUSIC:-/Volumes/Music}
echo "Running analysis on \"$MUSIC\""
.venv/bin/python -m rbassist.cli analyze --input "$MUSIC" --profile club_hifi_150s --device auto --workers 6 --rebuild-index
