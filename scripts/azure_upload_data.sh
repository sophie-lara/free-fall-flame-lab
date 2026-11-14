#!/usr/bin/env bash
# One-time (or deliberate) upload of local evidence data to Azure App Service.
# Dry run by default. Requires the Azure CLI (`az login`) and an existing web app.
#
#   scripts/azure_upload_data.sh <web-app-name> <resource-group>            # dry run
#   scripts/azure_upload_data.sh <web-app-name> <resource-group> --upload   # upload
#   ... --upload --overwrite   # replace data already on the server (stops the app briefly)
#
# Uploads data/raw, data/processed/{rag,visuals}, data/review and a consistent
# SQLite snapshot to /home/site/data. Never uploads .env, backups or eval outputs.
set -euo pipefail

app="${1:?web app name}"; group="${2:?resource group}"
upload=false; overwrite=false
for arg in "${@:3}"; do
  case "$arg" in
    --upload) upload=true ;;
    --overwrite) overwrite=true ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

root="$(cd "$(dirname "$0")/.." && pwd)"
stage="$(mktemp -d)"; trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/embeddings"
# Consistent snapshot even if the local app is running. The embedding vectors live
# inside this database, so uploading it is how the vectors reach Azure.
sqlite3 "$root/data/embeddings/rag.sqlite3" ".backup '$stage/embeddings/rag.sqlite3'"
# Copy only what the app serves (App Service Free tier has 1 GB of disk): indexed PDFs
# (matched by SHA-256, duplicates collapse), PSI experiment tables and capture
# manifests, figure crops referenced by the index, small RAG artifacts, review files.
"${PYTHON:-$root/.venv/bin/python}" - "$root" "$stage" <<'PY'
import hashlib, json, shutil, sqlite3, sys
from pathlib import Path
root, stage = Path(sys.argv[1]), Path(sys.argv[2])
data = root / "data"
db = sqlite3.connect(stage / "embeddings/rag.sqlite3")
wanted = {row[0] for row in db.execute("SELECT DISTINCT sha256 FROM pages")}
crops = {json.loads(p)["crop_path"] for (p,) in db.execute("SELECT payload FROM visual_artifacts")}
copied, seen = 0, set()
def put(source: Path) -> None:
    global copied
    target = stage / source.relative_to(data)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    copied += source.stat().st_size
for pdf in sorted((data / "raw").rglob("*.pdf")):
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if digest in wanted and digest not in seen:
        seen.add(digest)
        put(pdf)
for extra in [*(data / "raw").rglob("Experimental_table/*"), *(data / "raw").rglob("*.json*")]:
    if extra.is_file():
        put(extra)
for crop in crops:
    path = root / crop
    if path.is_file():
        put(path)
for part in ("processed/rag", "review"):
    for item in (data / part).rglob("*") if (data / part).is_dir() else []:
        if item.is_file():
            put(item)
missing = wanted - seen
print(f"Selected {copied / 1e6:.0f} MB; indexed PDFs {len(seen)}/{len(wanted)}; crops {len(crops)}")
if missing:
    print(f"WARNING: {len(missing)} indexed documents have no local PDF (page links will 404)")
PY
find "$stage" \( -name '.env*' -o -name '*.part' -o -name '.DS_Store' \) -delete
(cd "$stage" && zip -qr "$stage/data.zip" .)

echo "Package: $(du -h "$stage/data.zip" | cut -f1) for $app ($group) -> /home/site/data"
(cd "$stage" && find . -type f ! -name data.zip | sed 's|^\./||' | sort | awk -F/ '{print $1"/"$2}' | uniq -c)
if ! $upload; then echo "Dry run only. Re-run with --upload to send it."; exit 0; fi

host="$(az webapp show -n "$app" -g "$group" --query enabledHostNames -o tsv | tr '\t' '\n' | grep scm)"
token="$(az account get-access-token --query accessToken -o tsv)"
existing="$(curl -fsS -H "Authorization: Bearer $token" "https://$host/api/vfs/site/data/embeddings/" 2>/dev/null || true)"
if [ -n "$existing" ] && [ "$existing" != "[]" ] && ! $overwrite; then
  echo "The server already has an index in /home/site/data. Documents uploaded through" >&2
  echo "the hosted app would be replaced. Re-run with --overwrite to replace it." >&2
  exit 1
fi
$overwrite && az webapp stop -n "$app" -g "$group"
curl -fsS -X PUT -H "Authorization: Bearer $token" --data-binary @"$stage/data.zip" \
  "https://$host/api/zip/site/data/"
$overwrite && az webapp start -n "$app" -g "$group"
echo "Uploaded. Check https://${app}.azurewebsites.net/api/rag-status after signing in."
