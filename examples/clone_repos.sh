#!/usr/bin/env bash
# Clone or update all repos listed in sample_repos.txt.
# Repos land in a 'repos/' folder next to this script,
# so you can run it from any working directory.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOS_DIR="$SCRIPT_DIR/repos"
REPOS_FILE="$SCRIPT_DIR/sample_repos.txt"

mkdir -p "$REPOS_DIR"

while read -r full_name url; do
  # skip blank lines and comment lines
  [[ -z "${full_name:-}" || "${full_name}" == \#* ]] && continue
  repo_dir="$REPOS_DIR/${full_name//\//__}"
  if [ -d "$repo_dir/.git" ]; then
    echo "Updating  $full_name"
    git -C "$repo_dir" fetch --all --tags --prune -q
  else
    echo "Cloning   $full_name"
    git clone --depth 50 "$url" "$repo_dir"
  fi
done < "$REPOS_FILE"

echo ""
echo "Done. Repos are in: $REPOS_DIR"
