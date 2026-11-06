#!/usr/bin/env bash
#
# Despliegue del panel en el droplet.
#
# Decide solo que hace falta segun lo que cambio:
#   - solo static/  -> restart (el bundle de assets se regenera al arrancar)
#   - .py/.xml/.csv -> upgrade del modulo (hay registros o campos que migrar)
#   - compose       -> up -d (restart no toma variables de entorno nuevas)
#
# Idempotente: si no hay commits nuevos no toca nada.
set -euo pipefail

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

BRANCH=${DEPLOY_BRANCH:-main}
DB=${ODOO_DB_NAME:-lqa_panel_prod}
COMPOSE="docker compose --env-file .env.production -f docker-compose.prod.yml"

log() { printf '%s  %s\n' "$(date -u +%H:%M:%S)" "$*"; }
fail() { log "ERROR: $*"; exit 1; }

[ -f .env.production ] || fail "falta .env.production"

log "buscando cambios en origin/$BRANCH"
git fetch --quiet origin "$BRANCH"
BEFORE=$(git rev-parse HEAD)
AFTER=$(git rev-parse "origin/$BRANCH")

if [ "$BEFORE" = "$AFTER" ] && [ "${FORCE_DEPLOY:-0}" != "1" ]; then
    log "ya esta al dia en ${BEFORE:0:7}; nada que hacer"
    exit 0
fi

CHANGED=$(git diff --name-only "$BEFORE" "$AFTER" -- addons docker-compose.prod.yml config deploy || true)
if [ "${FORCE_DEPLOY:-0}" = "1" ]; then
    CHANGED=$(git ls-files addons docker-compose.prod.yml config deploy)
fi

log "${BEFORE:0:7} -> ${AFTER:0:7}"
git reset --hard --quiet "origin/$BRANCH"

if [ -z "$CHANGED" ]; then
    log "los commits no tocan el addon ni la infra; sin reinicio"
    exit 0
fi

NEEDS_RECREATE=0
NEEDS_UPGRADE=0
while IFS= read -r file; do
    [ -n "$file" ] || continue
    case "$file" in
        docker-compose.prod.yml|config/*|deploy/*)
            NEEDS_RECREATE=1 ;;
        addons/*/static/*)
            : ;;  # assets: alcanza con reiniciar
        addons/*.py|addons/*/*.py|addons/*/*/*.py|addons/*/*.xml|addons/*/*/*.xml|addons/*/*/*.csv)
            NEEDS_UPGRADE=1 ;;
    esac
done <<< "$CHANGED"

# Un upgrade toca el esquema: conviene tener de donde volver.
if [ "$NEEDS_UPGRADE" = "1" ] && [ "${SKIP_BACKUP:-0}" != "1" ]; then
    log "backup previo al upgrade"
    ./deploy/backup.sh >/dev/null || fail "fallo el backup; se aborta el deploy"
fi

if [ "$NEEDS_RECREATE" = "1" ]; then
    log "cambio la infraestructura: render de config y recreacion"
    ./deploy/render-odoo-config.sh
fi

if [ "$NEEDS_UPGRADE" = "1" ]; then
    log "upgrade del modulo lqa_admin_panel"
    $COMPOSE run --rm odoo odoo \
        --config=/etc/odoo/odoo.conf \
        --database="$DB" \
        --update=lqa_admin_panel \
        --stop-after-init \
        --no-http
fi

if [ "$NEEDS_RECREATE" = "1" ]; then
    $COMPOSE up -d odoo
else
    $COMPOSE restart odoo
fi

log "esperando que el panel responda"
for i in $(seq 1 30); do
    if $COMPOSE exec -T odoo curl -fsS -o /dev/null http://localhost:8069/web/login 2>/dev/null; then
        log "OK en ${AFTER:0:7}"
        exit 0
    fi
    sleep 2
done
fail "el panel no respondio tras el deploy de ${AFTER:0:7}"
