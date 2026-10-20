#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
tool_path="$repo_dir/tooling/openspec/node_modules/.bin/openspec"
if [[ ! -x "$tool_path" ]]; then
  echo "OpenSpec is missing. Run: npm --prefix tooling/openspec install" >&2
  exit 127
fi
cd -- "$repo_dir"
exec "$tool_path" "$@"
