#!/usr/bin/env bash
# Install the GitHub Actions workflows into .github/workflows/.
#
# These two files live in deploy/ because automated repo writes to
# .github/workflows/ are blocked by the GitHub App's security policy (workflow
# files can read repository secrets). Copy them in once, and commit.
#
#   bash tools/install_workflows.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/deploy"
DEST="$ROOT/.github/workflows"

mkdir -p "$DEST"
shopt -s nullglob
found=0

for f in "$SRC"/*.yml "$SRC"/*.yaml; do
  [ -e "$f" ] || continue
  name="$(basename "$f")"
  cp "$f" "$DEST/$name"
  echo "installed .github/workflows/$name"
  found=1
done

if [ "$found" -eq 0 ]; then
  echo "no workflow files found in $SRC" >&2
  exit 1
fi

echo
echo "Next:"
echo "  1. git add .github/workflows && git commit -m 'ci: install workflows'"
echo "  2. Settings -> Pages -> Source -> 'GitHub Actions'"
echo "  3. Settings -> Secrets and variables -> Actions -> Variables:"
echo "     VITE_API_URL = https://<your-render-service>.onrender.com"
