#!/usr/bin/env bash
set -euo pipefail

# Dry-run by default. This script only considers versioned release directories;
# it never traverses shared media, the database, cache, or .env.
APP_ROOT="${APP_ROOT:-/srv/recommendation-engine}"
KEEP_RELEASES="${KEEP_RELEASES:-5}"
APPLY=false
[[ "${1:-}" == "--apply" ]] && APPLY=true

RELEASES_DIR="${APP_ROOT%/}/releases"
CURRENT_LINK="${APP_ROOT%/}/current"
if [[ "$RELEASES_DIR" != /srv/*/releases || ! -d "$RELEASES_DIR" || ! "$KEEP_RELEASES" =~ ^[1-9][0-9]*$ ]]; then
  echo "Refusing unsafe cleanup: verify APP_ROOT, releases directory, and KEEP_RELEASES." >&2
  exit 2
fi

current="$(readlink -f "$CURRENT_LINK" 2>/dev/null || true)"
mapfile -t releases < <(find "$RELEASES_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -rn | cut -d' ' -f2-)
for ((index=KEEP_RELEASES; index<${#releases[@]}; index++)); do
  candidate="$(readlink -f "${releases[$index]}")"
  [[ "$candidate" == "$RELEASES_DIR"/* ]] || { echo "Refusing path outside releases: $candidate" >&2; exit 3; }
  [[ "$candidate" == "$current" ]] && continue
  if $APPLY; then
    rm -rf --one-file-system -- "$candidate"
    echo "Removed old release: $candidate"
  else
    echo "Would remove: $candidate"
  fi
done

$APPLY || echo "Dry run only. Re-run with --apply after reviewing every path above."
