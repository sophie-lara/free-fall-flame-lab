#!/bin/sh
set -eu

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

uv python install 3.12
uv sync --python 3.12 --all-groups --locked

if [ ! -f .env ]; then
  cp .env.example .env
fi

uv run python -m combustion_atlas.setup
uv run pytest
