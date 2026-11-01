#!/usr/bin/env bash
# Trusted test profile for execution worktrees.
#
# A worktree is a fresh checkout: ignored development state such as .venv and
# tooling/openspec/node_modules is absent, and the parent checkout's editable
# install would point Python at the wrong source tree. Provision this worktree
# only, then run the suite against it.
#
# specify-cli is pinned by git tag in normal development. Cloning it per
# worktree is slow and fails on a flaky network, so prefer a cached wheel:
#
#   uv tool install --force "specify-cli @ git+https://github.com/github/spec-kit.git@v1.2.1"
#   SPECIFY_WHEEL_DIR=$HOME/.cache/specrunway/wheels
#   mkdir -p "$SPECIFY_WHEEL_DIR"
#   pip download --no-deps -d "$SPECIFY_WHEEL_DIR" \
#     "specify-cli @ git+https://github.com/github/spec-kit.git@v1.2.1"
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

wheel_dir="${SPECIFY_WHEEL_DIR:-$HOME/.cache/specrunway/wheels}"

if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
  .venv/bin/python -m ensurepip --upgrade >/dev/null
  .venv/bin/python -m pip install --quiet --upgrade pip
fi

.venv/bin/python -m pip install --quiet -e '.[dev]'

if ! .venv/bin/python -c 'import specify_cli' >/dev/null 2>&1; then
  if compgen -G "$wheel_dir/specify_cli-*.whl" >/dev/null; then
    .venv/bin/python -m pip install --quiet --no-index \
      --find-links "$wheel_dir" 'specify-cli==1.2.1'
  else
    .venv/bin/python -m pip install --quiet --retries 3 --timeout 30 \
      'specify-cli @ git+https://github.com/github/spec-kit.git@v1.2.1' || {
      echo "specify-cli install failed; pre-seed $wheel_dir (see this file's header)" >&2
      exit 1
    }
  fi
fi

if [[ ! -x tooling/openspec/node_modules/.bin/openspec ]]; then
  npm ci --prefix tooling/openspec >/dev/null
fi

.venv/bin/python -m pytest -q
