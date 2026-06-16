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

./deploy/render-odoo-config.sh

$COMPOSE up -d db
$COMPOSE run --rm odoo \
    odoo \
    --config=/etc/odoo/odoo.conf \
    --database="$ODOO_DB_NAME" \
    --init=lqa_admin_panel \
    --stop-after-init \
    --no-http

cat > /tmp/lqa-set-admin-password.py <<'PY'
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

$COMPOSE run --rm -T \
    -e ODOO_INITIAL_ADMIN_PASSWORD="$ODOO_INITIAL_ADMIN_PASSWORD" \
    -v /tmp/lqa-set-admin-password.py:/tmp/lqa-set-admin-password.py:ro \
    --entrypoint /bin/sh \
    odoo \
    -c "odoo shell -c /etc/odoo/odoo.conf -d $ODOO_DB_NAME --no-http < /tmp/lqa-set-admin-password.py"

$COMPOSE up -d
echo "Production database initialized."
