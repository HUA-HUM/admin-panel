# Panel Admin - Lo Quiero Aca

Base de panel comercial construida sobre Odoo + Docker.

## Que incluye

- Odoo 18 con Postgres 16 en Docker Compose.
- Addon custom `lqa_admin_panel`.
- Menu principal `Panel Comercial`.
- Navbar compacto y sidebar desplegable para navegar modulos y secciones.
- Dashboard inicial con modulos:
  - `MercadoLibre`
  - `Automeli`
  - `Retailers`
- Seccion `MercadoLibre / Catalogo` conectada a la API de rendimiento:
  - Primera pagina de hasta 100 productos.
  - Tarjetas con precio, stock, facturacion, ordenes, unidades, visitas y conversion.
  - Filtros por busqueda, marca, categoria, dominio, estado, condicion, SKU,
    ordenes, visitas, facturacion, fechas y ordenamiento.
  - Seleccion multiple de cards para eliminacion masiva con confirmacion.
- Seccion `MercadoLibre / Eliminador`:
  - Carga de MLAs por texto o archivo CSV.
  - Confirmacion obligatoria antes de ejecutar.
  - Historial persistente por lote y por publicacion.
- Seccion `MercadoLibre / Central de Promociones`:
  - Resumen por tipo de promocion: SMART, DEAL y PRE_NEGOTIATED.
  - Listado paginado de promociones con estado, precios, economia y fechas.
  - Catalogo de campanas disponibles con candidatos por promocion.
  - Ordenes con aporte ML y analytics por fecha.
  - Acciones operativas en segundo plano: sync, activacion, desactivacion,
    reintento de desactivaciones fallidas y sync de una promocion puntual.
  - Historial persistente de ejecuciones y visor Datadog Live Tail.
- Seccion `Automeli / Catalogo` conectada a la API de snapshots:
  - Filtros basicos y avanzados.
  - Cards con costos, stock, peso y estados Amazon/MercadoLibre.
- Modulo `Retailers`:
  - Dashboard local de marketplaces: Google Merchant, Fravega, OnCity y Megatone.
  - Pantalla por marketplace con tabs `Products`, `Imports` y `Status`.
  - Products consulta productos paginados por marketplace, SKU y estado.
  - Imports permite disparar importaciones asincronicas con confirmacion e historial.
  - Status muestra la distribucion visual de estados de publicaciones.
- Grupos de seguridad para usuarios comerciales y administradores del panel.
- Seccion `Configuracion / Usuarios`:
  - Alta manual de usuarios internos con email/login y contrasena.
  - Asignacion de permisos comercial o administrador del panel.
  - Activacion, desactivacion y cambio manual de contrasena.
- Configuracion preparada para APIs internas: entorno, URL base, token, rutas por modulo y timeout.

## Levantar el proyecto

```bash
docker compose up -d
```

Luego abrir:

```text
http://localhost:8069
```

Para crear una base de prueba ya con el addon instalado:

```bash
docker exec lqa-panel-odoo odoo -c /etc/odoo/odoo.conf -d lqa_panel_test -i lqa_admin_panel --stop-after-init --no-http
```

Luego entrar con:

```text
Base: lqa_panel_test
Usuario: admin
Password: admin
```

Si preferis crearlo desde la UI de Odoo:

1. Crear una base de datos.
2. Entrar en modo desarrollador.
3. Ir a `Apps`.
4. Actualizar la lista de aplicaciones.
5. Instalar `LQA Admin Panel`.

Usuario administrador inicial de Odoo: el que crees al crear la base.

## Despliegue de produccion

La configuracion productiva usa PostgreSQL, Odoo multiproceso y Caddy como
proxy HTTPS:

```bash
cp .env.production.example .env.production
chmod 600 .env.production
```

Completar contrasenas y credenciales en `.env.production`. Para inicializar
una base nueva e instalar el addon:

```bash
chmod +x deploy/*.sh
./deploy/bootstrap-database.sh
```

Para actualizaciones posteriores:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml \
  run --rm odoo odoo -c /etc/odoo/odoo.conf -d lqa_panel_prod \
  -u lqa_admin_panel --stop-after-init --no-http
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
```

Backup manual:

```bash
./deploy/backup.sh
```

El DNS de `admin.loquieroaca.com` debe apuntar a la IP publica del
servidor. Caddy obtiene y renueva automaticamente el certificado TLS.

## Configurar usuarios comerciales

En `Ajustes > Usuarios`, asignar uno de estos permisos:

- `Panel Comercial / Usuario comercial`
- `Panel Comercial / Administrador del panel`

El administrador del panel hereda el acceso comercial y puede editar la configuracion funcional.

Tambien se pueden crear y editar accesos desde `Panel Comercial > Configuracion > Usuarios`.
Esta pantalla no requiere SMTP porque permite definir la contrasena manualmente.

## Configurar APIs internas

Ir a `Ajustes > Panel Comercial` y completar:

- Entorno: desarrollo, staging o produccion.
- URL base de API.
- Token interno.
- Ruta MercadoLibre.
- Ruta Automeli.
- URL de Catalogo MercadoLibre.
- URL y clave interna del Eliminador MercadoLibre.
- URLs de Central de Promociones MercadoLibre.
- URLs de ordenes y analytics de aporte ML.
- Timeout extendido de Central de Promociones.
- URLs de acciones de Central de Promociones.
- URL base y servicio de Datadog Live Tail.
- URL de Catalogo Automeli.
- URLs base Madre y Products para Retailers.
- Timeout.
- Variables de entorno Retailers:
  - `NEXT_PUBLIC_MADRE_API_URL=https://api.madre.loquieroaca.com`
  - `NEXT_PUBLIC_PRODUCTS_API_URL=https://api.products.loquieroaca.com`

El dashboard lee esta configuracion sin mostrar secretos. Las llamadas quedan
centralizadas en `lqa.api.client`. El catalogo de MercadoLibre usa por defecto:

```text
https://catalog-meli.loquieroaca.com/analytics/products/performance
```

La Central de Promociones usa por defecto:

```text
http://cpe.loquieroaca.com/promotions/stats
http://cpe.loquieroaca.com/promotions
http://cpe.loquieroaca.com/promotions/catalogs
https://api.madre.loquieroaca.com/api/mercadolibre/orders/aporte-ml
https://api.madre.loquieroaca.com/api/mercadolibre/orders/analytics/aporte-ml/timeseries
http://cpe.loquieroaca.com/promotions/sync
http://cpe.loquieroaca.com/promotions/activate
http://cpe.loquieroaca.com/promotions/deactivate
http://cpe.loquieroaca.com/promotions/deactivate-failed
http://cpe.loquieroaca.com/promotions/sync-one
https://us5.datadoghq.com/logs/livetail
```

Las acciones de Central de Promociones se encolan en Odoo y se ejecutan en un
thread de backend para no bloquear la pantalla mientras CPE procesa. Solo el
grupo `Panel Comercial / Administrador del panel` puede dispararlas.

Retailers usa por defecto:

```text
https://api.madre.loquieroaca.com/api/internal/marketplace/products/items/all
https://api.madre.loquieroaca.com/api/internal/product-sync/runs
https://api.madre.loquieroaca.com/api/internal/marketplace/products/{marketplace}/status
https://api.products.loquieroaca.com/api/internal/import/{marketplace}/run
```

Si el servicio de imports vive en otro host, configurar `URL Products Retailers`
en `Ajustes > Panel Comercial`.

## Estructura

```text
addons/lqa_admin_panel/
  models/
    api_client.py
    automeli_catalog_item.py
    dashboard_service.py
    mercadolibre_deletion.py
    mercadolibre_catalog_service.py
    mercadolibre_promotions_service.py
    panel_module.py
    res_config_settings.py
    retailers_service.py
    user_management_service.py
  views/
    automeli_catalog_views.xml
    panel_data.xml
    panel_menu_views.xml
    panel_module_views.xml
    res_config_settings_views.xml
  security/
    ir.model.access.csv
    lqa_security.xml
  static/src/
    js/dashboard.js
    js/mercadolibre_catalog.js
    js/mercadolibre_deleter.js
    js/mercadolibre_promotions.js
    js/automeli_catalog.js
    js/retailers.js
    js/navigation.js
    scss/dashboard.scss
    scss/mercadolibre_catalog.scss
    scss/mercadolibre_deleter.scss
    scss/mercadolibre_promotions.scss
    scss/automeli_catalog.scss
    scss/retailers.scss
    xml/dashboard.xml
    xml/mercadolibre_catalog.xml
    xml/mercadolibre_deleter.xml
    xml/mercadolibre_promotions.xml
    xml/automeli_catalog.xml
    xml/retailers.xml
```

## Proximo paso recomendado

Definir los contratos de API para:

- Estado/resumen de MercadoLibre.
- Sincronizacion de catalogo Automeli.
- Autenticacion y scopes del token interno.
# admin-panel
