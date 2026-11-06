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

# El commit que quedo efectivamente desplegado, que no es lo mismo que el que
# esta en el working tree: si el deploy aborta despues del reset, HEAD ya
# avanzo pero el modulo nunca se actualizo. Comparar contra HEAD daba ese
# estado a medias por bueno.
STATE_FILE=".deploy-state"

log "buscando cambios en origin/$BRANCH"
git fetch --quiet origin "$BRANCH"
BEFORE=$(cat "$STATE_FILE" 2>/dev/null || git rev-parse HEAD)
AFTER=$(git rev-parse "origin/$BRANCH")

if [ "$BEFORE" = "$AFTER" ] && [ "${FORCE_DEPLOY:-0}" != "1" ]; then
    log "ya esta desplegado ${BEFORE:0:7}; nada que hacer"
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
    echo "$AFTER" > "$STATE_FILE"
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

# Un upgrade toca el esquema: conviene tener de donde volver. Pero el dump
# ronda los 600 MB y tarda tres minutos, asi que no tiene sentido repetirlo en
# deploys seguidos: uno reciente sirve igual para volver atras.
if [ "$NEEDS_UPGRADE" = "1" ] && [ "${SKIP_BACKUP:-0}" != "1" ]; then
    RECENT=$(find "${BACKUP_DIR:-backups}" -maxdepth 1 -name 'database-*.dump' \
        -mmin -${BACKUP_MAX_AGE_MIN:-60} 2>/dev/null | head -1)
    if [ -n "$RECENT" ]; then
        log "hay un backup de hace menos de ${BACKUP_MAX_AGE_MIN:-60} min; se reutiliza"
    else
        log "backup previo al upgrade"
        ./deploy/backup.sh >/dev/null || fail "fallo el backup; se aborta el deploy"
    fi
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
fi
# Siempre reiniciar, incluso despues de un up -d: compose no recrea el
# contenedor si la configuracion no cambio, y el codigo Python solo se carga
# al arrancar el proceso. Sin esto el upgrade corria pero Odoo seguia
# sirviendo la version anterior.
$COMPOSE restart odoo

log "esperando que el panel responda"
READY=0
for i in $(seq 1 30); do
    if $COMPOSE exec -T odoo curl -fsS -o /dev/null http://localhost:8069/web/login 2>/dev/null; then
        READY=1
        break
    fi
    sleep 2
done
[ "$READY" = "1" ] || fail "el panel no respondio tras el deploy de ${AFTER:0:7}"

# Que responda no prueba que tenga el codigo nuevo: un Odoo viejo contesta
# igual. Comparamos la version que quedo instalada contra el manifiesto.
MANIFEST_VERSION=$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
    addons/lqa_admin_panel/__manifest__.py | head -1)
INSTALLED_VERSION=$($COMPOSE exec -T db psql -U "${POSTGRES_USER:-odoo}" -d "$DB" -tAc \
    "SELECT latest_version FROM ir_module_module WHERE name='lqa_admin_panel'" 2>/dev/null | tr -d '[:space:]')

if [ -n "$MANIFEST_VERSION" ] && [ -n "$INSTALLED_VERSION" ] \
   && [ "$MANIFEST_VERSION" != "$INSTALLED_VERSION" ]; then
    fail "el modulo quedo en $INSTALLED_VERSION y el repo trae $MANIFEST_VERSION"
fi

echo "$AFTER" > "$STATE_FILE"
log "OK en ${AFTER:0:7} (modulo ${INSTALLED_VERSION:-?})"
exit 0
