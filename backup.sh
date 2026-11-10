#!/usr/bin/env bash
# Backup diário do banco do radar. Mantém os últimos 14 arquivos.
# Agende no cron, ex.: 30 4 * * * /caminho/radar-ofertas/backup.sh
set -euo pipefail
cd "$(dirname "$0")"
DEST=${BACKUP_DIR:-./backups}
mkdir -p "$DEST"
FILE="$DEST/radar-$(date +%F).sql.gz"
docker compose exec -T db pg_dump -U radar radar | gzip > "$FILE.tmp"
mv "$FILE.tmp" "$FILE"
ls -1t "$DEST"/radar-*.sql.gz | tail -n +15 | xargs -r rm --
echo "ok $FILE $(du -h "$FILE" | cut -f1)"
