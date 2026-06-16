#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

if [ ! -f .env.production ]; then
    echo "Missing .env.production" >&2
    exit 1
fi

set -a
. ./.env.production
set +a

cp config/odoo.prod.conf config/odoo.runtime.conf
printf '\nadmin_passwd = %s\ndb_password = %s\n' \
    "$ODOO_MASTER_PASSWORD" \
    "$POSTGRES_PASSWORD" >> config/odoo.runtime.conf

chmod 640 config/odoo.runtime.conf

if command -v docker >/dev/null 2>&1; then
    ODOO_UID=$(docker run --rm --entrypoint id "${ODOO_IMAGE:-odoo:18.0}" -u odoo)
    ODOO_GID=$(docker run --rm --entrypoint id "${ODOO_IMAGE:-odoo:18.0}" -g odoo)
    chown "$ODOO_UID:$ODOO_GID" config/odoo.runtime.conf
fi

echo "Rendered config/odoo.runtime.conf"
