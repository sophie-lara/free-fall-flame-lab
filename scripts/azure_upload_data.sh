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
mkdir -p "$stage/embeddings" "$stage/processed"
cp -R "$root/data/raw" "$stage/raw"
for part in rag visuals; do
  [ -d "$root/data/processed/$part" ] && cp -R "$root/data/processed/$part" "$stage/processed/$part"
done
[ -d "$root/data/review" ] && cp -R "$root/data/review" "$stage/review"
# Consistent snapshot even if the local app is running.
sqlite3 "$root/data/embeddings/rag.sqlite3" ".backup '$stage/embeddings/rag.sqlite3'"
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
