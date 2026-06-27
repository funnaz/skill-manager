#!/usr/bin/env bash
set -euo pipefail

SCOPE="${1:-grok}"
REPO="https://github.com/funnaz/skill-manager.git"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -f "$ROOT/cli.py" ]]; then
  python "$ROOT/cli.py" install --git "$REPO" --scope "$SCOPE"
  pip install -r "$ROOT/requirements.txt"
  echo "Skill Manager installed to scope: $SCOPE"
  exit 0
fi

TMP="$(mktemp -d)"
git clone --depth 1 "$REPO" "$TMP"
python "$TMP/cli.py" install --git "$REPO" --scope "$SCOPE"
pip install -r "$TMP/requirements.txt"
rm -rf "$TMP"
echo "Skill Manager installed to scope: $SCOPE"