
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")" && pwd)"
osascript -e 'tell application "Terminal" to do script "cd \"'$DIR'\"; bash run_analyze.sh; read -n 1 -s -r -p \"Press any key to close...\" "'
