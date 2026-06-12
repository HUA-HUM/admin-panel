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

COMPOSE="docker compose --env-file .env.production -f docker-compose.prod.yml"

$COMPOSE up -d db
$COMPOSE run --rm odoo \
    odoo \
    --config=/etc/odoo/odoo.conf \
    --database="$ODOO_DB_NAME" \
    --init=lqa_admin_panel \
    --stop-after-init \
    --no-http \
    --admin-passwd="$ODOO_MASTER_PASSWORD" \
    --db_password="$POSTGRES_PASSWORD"

$COMPOSE run --rm -T \
    -e ODOO_INITIAL_ADMIN_PASSWORD="$ODOO_INITIAL_ADMIN_PASSWORD" \
    odoo \
    odoo shell \
    --config=/etc/odoo/odoo.conf \
    --database="$ODOO_DB_NAME" \
    --no-http \
    --admin-passwd="$ODOO_MASTER_PASSWORD" \
    --db_password="$POSTGRES_PASSWORD" <<'PY'
import os

admin = env.ref("base.user_admin")
admin.write(
    {
        "login": "admin",
        "password": os.environ["ODOO_INITIAL_ADMIN_PASSWORD"],
    }
)
env.cr.commit()
PY

$COMPOSE up -d
echo "Production database initialized."
