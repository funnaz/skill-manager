#!/usr/bin/env bash
set -euo pipefail

SCOPE="${1:-grok}"
REPO="https://github.com/funnaz/skill-manager.git"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

case "$SCOPE" in
  grok|agents|claude|codex|cursor) ;;
  *)
    echo "Invalid scope: $SCOPE" >&2
    echo "Valid scopes: grok, agents, claude, codex, cursor" >&2
    exit 2
    ;;
esac

if [[ -f "$ROOT/cli.py" ]]; then
  pip install -r "$ROOT/requirements.txt"
  python "$ROOT/cli.py" install --git "$REPO" --scope "$SCOPE"
  echo "Skill Manager installed to scope: $SCOPE"
  exit 0
fi

TMP="$(mktemp -d)"
git clone --depth 1 "$REPO" "$TMP"
pip install -r "$TMP/requirements.txt"
python "$TMP/cli.py" install --git "$REPO" --scope "$SCOPE"
rm -rf "$TMP"
echo "Skill Manager installed to scope: $SCOPE"
