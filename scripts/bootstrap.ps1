param(
    [switch]$Check
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required: https://docs.astral.sh/uv/getting-started/installation/"
}

uv python install 3.12
uv sync --python 3.12 --all-groups --locked

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
}

if ($Check) {
    uv run python -m combustion_atlas.setup
    uv run pytest
}
