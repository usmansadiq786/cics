#!/usr/bin/env bash
set -euo pipefail

mkdir -p repos

while read -r full_name url; do
  [ -z "${full_name:-}" ] && continue
  repo_dir="repos/${full_name//\//__}"
  if [ -d "$repo_dir/.git" ]; then
    echo "Updating $full_name"
    git -C "$repo_dir" fetch --all --tags --prune
  else
    echo "Cloning $full_name"
    git clone --depth 50 "$url" "$repo_dir"
  fi
done < sample_repos.txt
