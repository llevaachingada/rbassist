#!/usr/bin/env bash
set -euo pipefail

# Usage: scripts/git-sync-status.sh [remote] [branch]
# Defaults: remote="origin", branch=current branch. The script fetches the
# remote and reports how many commits the branch is ahead/behind its matching
# remote branch. Pass an explicit branch to compare a different local branch
# against the same-named remote branch (e.g., comparing your fork's "main" to
# upstream's "main").

remote=${1:-origin}

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "This script must be run inside a git repository." >&2
  exit 1
fi

branch=${2:-$(git rev-parse --abbrev-ref HEAD)}

if [[ "$branch" == "HEAD" ]]; then
  echo "Detached HEAD; pass an explicit branch name (e.g., 'main')." >&2
  exit 1
fi

if ! git remote get-url "$remote" >/dev/null 2>&1; then
  echo "Remote '$remote' is not configured. Add it with:" >&2
  echo "  git remote add $remote <url>" >&2
  exit 1
fi

echo "Fetching $remote..." >&2
git fetch "$remote" >&2

if ! git show-ref --verify --quiet "refs/heads/$branch"; then
  echo "Local branch '$branch' does not exist. Available local branches:" >&2
  git branch --list >&2
  echo "Create or switch to a matching branch, or fetch it: git switch -c $branch --track $remote/$branch" >&2
  exit 1
fi

upstream="$remote/$branch"
if ! git show-ref --verify --quiet "refs/remotes/$upstream"; then
  echo "Remote branch '$upstream' does not exist. Available remote branches:" >&2
  git branch -r >&2
  exit 1
fi

read behind ahead <<<"$(git rev-list --left-right --count "$upstream...$branch")"

cat <<REPORT
Local branch : $branch
Remote branch: $upstream
Ahead by     : $ahead commit(s)
Behind by    : $behind commit(s)
REPORT

echo "Recent remote commits (latest first):" >&2
git log --oneline --decorate -5 "$upstream" >&2

echo "Recent local commits (latest first):" >&2
git log --oneline --decorate -5 "$branch" >&2

exit 0
