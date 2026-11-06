#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BACKUP_DIR=${BACKUP_DIR:-"$ROOT_DIR/backups"}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)

cd "$ROOT_DIR"

if [ ! -f .env.production ]; then
    echo "Missing .env.production" >&2
    exit 1
fi

set -a
. ./.env.production
set +a

mkdir -p "$BACKUP_DIR"

docker compose --env-file .env.production -f docker-compose.prod.yml \
    exec -T db \
    pg_dump -U "$POSTGRES_USER" -d "$ODOO_DB_NAME" -Fc \
    > "$BACKUP_DIR/database-$STAMP.dump"

docker compose --env-file .env.production -f docker-compose.prod.yml \
    exec -T odoo \
    tar -C /var/lib/odoo -czf - . \
    > "$BACKUP_DIR/filestore-$STAMP.tar.gz"

find "$BACKUP_DIR" -type f -mtime +14 \
    \( -name "database-*.dump" -o -name "filestore-*.tar.gz" \) \
    -delete

# Techo por cantidad ademas del de antiguedad: con varios deploys por dia la
# regla de 14 dias sola puede acumular decenas de GB.
KEEP=${BACKUP_KEEP:-10}
for pattern in "database-*.dump" "filestore-*.tar.gz"; do
    find "$BACKUP_DIR" -maxdepth 1 -name "$pattern" -printf '%T@ %p\n' 2>/dev/null \
        | sort -rn | tail -n +$((KEEP + 1)) | cut -d' ' -f2- \
        | while IFS= read -r old_file; do rm -f "$old_file"; done
done

echo "Backup completed: $STAMP"
