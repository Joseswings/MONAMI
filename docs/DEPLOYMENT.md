# Monami: demo de pitch preparada y reiniciable

Estado del hito 9: código y configuración preparados. La conexión real a Supabase, la migración
remota y el despliegue se verificarán cuando se configuren las credenciales y el proveedor.
Repositorio indicado: https://github.com/Joseswings/MONAMI.

## Alcance de esta demo

React + Vite + TypeScript → FastAPI → PostgreSQL en Supabase. React solo conoce la URL pública
de FastAPI. No hay cliente Supabase, claves de base ni acceso directo a PostgreSQL en el navegador.

El escenario es compartido entre participantes, con una única EmpresaTest y cinco actores ficticios.
El botón **Explorar demo** permite entrar sin contraseña y cambiar de rol para presentar el recorrido.
Una clave privada del presentador permite restaurarlo. Esto es acceso público a una demo,
no registro de clientes o empleados reales.

Se guardan pedidos, camiones, viajes, incidentes, terceros, historiales e idempotencia en un agregado
JSONB versionado en `monami.pitch_scenarios`. Cada operación se ejecuta bajo una transacción y
bloqueo de fila PostgreSQL. Los datos persisten entre procesos y reinicios de FastAPI. Es una decisión
para acotar el pitch: todavía no hay tablas operativas normalizadas ni consultas analíticas logísticas.

Las sesiones guardan únicamente el hash del token en `monami.pitch_sessions`. El token del navegador
vive en memoria: recargar pide pulsar **Explorar demo** de nuevo, conservando los datos del escenario. No hay sesiones
por empleado ni permiso administrativo real al seleccionar el actor empresa; todos los participantes
con acceso pueden ensayar los roles ficticios. El reinicio exige además la clave del presentador.

Límites: 100 pedidos por escenario, 2 MB de estado, datos ficticios, seguimiento manual, cartografía
geométrica y un escenario compartido. No se envían mensajes, cobran servicios ni coordinan entregas reales.
Una aplicación comercial completa requiere otro alcance de identidad, permisos, modelo de datos y operación.

## 1. Datos que hacen falta

- URL PostgreSQL real del proyecto Supabase para el backend, con contraseña codificada y SSL.
- Opcionalmente, otra conexión con permisos DDL para Alembic: `MIGRATION_DATABASE_URL`.
- Una clave privada del presentador para reiniciar, de 24 a 256 caracteres.
- Proveedor del backend y URL HTTPS final de ambos servicios; puede decidirse después de preparar la base.
- Una base PostgreSQL distinta para ejecutar las pruebas de integración.

No hace falta un conector Supabase ni claves `anon` o `service_role`. No compartir contraseñas en el chat,
Git, capturas ni variables `VITE_*`. Los archivos `.env` locales permanecen excluidos de Git.

## 2. Configurar Supabase y variables locales

En Supabase abrir el proyecto → **Connect**. Para un backend persistente se admite conexión directa;
si no hay IPv6, usar **Session pooler**. Para Vercel Functions, usar **Transaction pooler**. Se desactivan
prepared statements en Psycopg para admitir este último modo. Usar la cadena de ese proyecto, sin
inventar host, usuario o región. Referencia: [conexiones PostgreSQL en Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres).

En `backend/.env.local`, completar lo siguiente. Este archivo tiene prioridad sobre `.env`; las
variables del proceso tienen prioridad sobre ambos. Conservar una copia privada del archivo local
si se quiere volver a la simulación vacía de los hitos anteriores.

```dotenv
DEMO_MODE=false
PITCH_MODE=true
PITCH_SCENARIO_ID=monami-pitch
DATABASE_URL=postgresql+psycopg://USUARIO:CONTRASENA_CODIFICADA@HOST:PUERTO/postgres?sslmode=require
PITCH_RESET_KEY=REPLACE_WITH_RANDOM_PRESENTER_KEY
CORS_ORIGINS=["http://localhost:5173"]
SESSION_TTL_MINUTES=480
```

Sustituir `postgresql://` de la cadena de Supabase por `postgresql+psycopg://`. Conservar su usuario,
host, puerto y base. Añadir `?sslmode=require`, o `&sslmode=require` si ya tiene parámetros. Codificar
caracteres reservados de la contraseña, por ejemplo `@` como `%40` y `#` como `%23`, sin codificar la URL completa.

Los espectadores no necesitan una clave: el botón **Explorar demo** crea una sesión pública para
recorrer los roles ficticios. `PITCH_ACCESS_KEY` ya no se utiliza; si permanece en archivos locales
o en el proveedor, se ignora. Solo el reinicio requiere una clave privada.

Para generar `PITCH_RESET_KEY`, ejecutar localmente desde `backend/` una vez y copiar el resultado
solo a esa variable. Mantenerla privada: permite restaurar el escenario compartido.

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

Si la conexión de aplicación tiene permisos limitados, configurar además `MIGRATION_DATABASE_URL`
con la cuenta que puede crear tablas. Para una primera demo en un proyecto dedicado puede utilizarse
la conexión de su propietario, exclusivamente desde el backend. No exponer el esquema `monami` en
la API de datos de Supabase. Las dos tablas de pitch activan RLS sin políticas de acceso público.

Si luego se usa una cuenta PostgreSQL limitada, necesita permisos sobre ambas tablas y una política RLS
específica para el identificador del escenario. Un `GRANT` por sí solo no supera RLS. La cuenta propietaria
usada para las migraciones no requiere esa política. No configurar credenciales de aplicación a ciegas.

En `frontend/.env` para el ensayo local:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 3. Aplicar esquema y cargar el escenario explícitamente

Desde `backend/`, después de completar las variables:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.pitch_seed
```

La revisión esperada es `0002_pitch`. Se conservan las tablas de identidad del hito 1 y se añaden las
dos tablas de pitch. La migración no carga pedidos. Repetir `upgrade head` no repite cambios; repetir
`app.pitch_seed` conserva el escenario existente. Arrancar el servidor no migra ni restaura datos.
`app.seed` pertenece a las cuentas del hito 1 y no es el cargador de este escenario.

Si algo falla, no borrar tablas ni recrear el proyecto automáticamente: comprobar conexión, revisión y
permisos. La carga y el reinicio solo escriben la fila del `PITCH_SCENARIO_ID` configurado; no eliminan
usuarios, organizaciones, otros escenarios ni otras tablas del proyecto.

## 4. Ensayo local con PostgreSQL real

Arrancar FastAPI desde `backend/` y React desde `frontend/`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
npm.cmd run dev -- --port 5173 --strictPort
```

Abrir http://localhost:5173 y pulsar **Explorar demo**, sin introducir credenciales. Aparece:

| Situación inicial | Uso durante el pitch |
| --- | --- |
| Dos pedidos en un viaje al 25%, Camión 1 y Conductor de prueba | Bloqueo, alternativa, avance y entrega |
| Pedido listo de 61 unidades | Flota sin capacidad: solicitar aliado |
| Pedido recibido | Confirmación o solicitud de corrección |
| Pedido en preparación | Fechas y listo para salir |
| Pedido entregado por tercero | Ejemplo de tracker completo e historial |

Las fechas se regeneran al cargar o reiniciar. Los códigos son nuevos en cada reinicio. Los perfiles
de ambos clientes consultan solo sus pedidos dentro de la simulación. Todos los contactos son ficticios.

Probar cambios desde empresa, conductor y cliente; reiniciar solo FastAPI y comprobar que se conservan.
Para restaurar, usar **Reiniciar presentación**, introducir `PITCH_RESET_KEY`, marcar la confirmación y
restaurar. Afecta a todos los participantes de ese escenario. Las otras pestañas actualizan su versión
cada 15 segundos; también pueden usar **Actualizar escenario**. Las acciones con una versión anterior
se rechazan con `409`, aunque una revisión de pedido o planificación coincida por casualidad.

## 5. Despliegue: dos proyectos del mismo repositorio

El proveedor todavía está por decidir. Hay configuración para las siguientes alternativas; no se han
creado servicios remotos, contratado planes ni publicado automáticamente el repositorio.

### Vercel para frontend y backend

Vercel soporta FastAPI como función Python y su ciclo de vida. Hobby tiene restricciones de uso
personal no comercial; confirmar que el caso del pitch es elegible antes de contar con ese plan.
Referencias: [FastAPI](https://vercel.com/docs/frameworks/backend/fastapi),
[Hobby](https://vercel.com/docs/plans/hobby).

1. Subir los cambios revisados al repositorio `Joseswings/MONAMI`, sin `.env` ni herramientas locales.
2. Importarlo como proyecto de backend, con **Root Directory: `backend`**. Se incluye `vercel.json`
   y `[tool.vercel]` apunta a `app.main:app`. Python 3.12 y dependencias están definidos por el proyecto.
3. Configurar las variables privadas del backend: las del paso 2, sin `DEMO_MODE=true`. Para Vercel,
   usar el pooler de transacciones de Supabase. La función tiene un límite configurado de 30 segundos.
4. Aplicar la migración y la carga del paso 3 desde el entorno local configurado, una sola vez para
   la misma base. No hacerlas en el Build Command ni en el arranque de cada función.
5. Crear otro proyecto desde el mismo repositorio con **Root Directory: `frontend`**, framework Vite,
   instalación `npm ci`, build `npm run build` y salida `dist`.
6. Configurar **solo** `VITE_API_BASE_URL=https://URL-REAL-DEL-BACKEND` en ese proyecto.
7. Con la URL de React, ajustar `CORS_ORIGINS=["https://URL-REAL-DEL-FRONTEND"]` en el backend.
8. Desplegar nuevamente si cambian esas variables. No usar `*` ni una ruta después del origen.
9. Si está activada la protección de despliegues del proveedor, comprobar que las peticiones del
   frontend pueden alcanzar la API. No poner tokens de bypass del proveedor en el navegador.

#### Activar el acceso público en un despliegue existente

1. Subir esta versión a GitHub y publicar el **backend** con el commit actualizado. Comprobar
   el commit de origen del despliegue: redesplegar una publicación antigua conserva su código.
2. Publicar el **frontend** con el mismo commit para mostrar el botón **Explorar demo**.
   Publicar primero el backend evita que el botón nuevo encuentre una API que todavía exija clave.
3. Con ambos servicios actualizados, se puede eliminar `PITCH_ACCESS_KEY` de las variables del
   backend y de los archivos locales. Es opcional: la nueva versión ignora esa variable.
   Mantener `PITCH_RESET_KEY`, `DATABASE_URL` y las demás variables de conexión y CORS.
4. Abrir la demo o recargar y comprobar que **Explorar demo** permite entrar sin contraseña,
   cambiar roles y consultar el escenario. Comprobar que reiniciar todavía exige la clave
   del presentador. Las sesiones existentes siguen siendo válidas hasta salir o vencer.

No requiere migraciones ni volver a cargar el escenario. El acceso público mantiene el progreso
compartido: las acciones de cualquier visitante afectan al escenario de todos los participantes.

### Cloudflare Pages para React y un backend Docker

1. En Cloudflare Pages conectar el mismo repositorio. **Root directory: `frontend`**, comando de
   build `npm run build`, directorio publicado `dist`, Node 24.
2. Definir `VITE_API_BASE_URL` con la URL HTTPS real del backend. El archivo `_headers` incluido
   configura encabezados del sitio en Pages. La navegación actual usa fragmentos `#`, sin rewrites extra.
3. Para FastAPI, construir `backend/Dockerfile` con contexto `backend`. El contenedor escucha en
   `0.0.0.0:$PORT`, o 8000 si no se define puerto. Excluye `.env`, pruebas, cachés y herramientas locales.
4. Introducir las variables privadas del backend en el proveedor del contenedor; configurar como
   origen CORS la URL Pages. La base permanece en Supabase.
5. Cloudflare Containers también puede ejecutar el contenedor, pero requiere Workers de pago y
   configuración adicional de Worker y secretos. No se incluye ese despliegue hasta elegirlo.

Referencias: [React en Pages](https://developers.cloudflare.com/pages/framework-guides/react/),
[Containers](https://developers.cloudflare.com/containers/).

Build Docker, cuando Docker Desktop esté activo:

```powershell
docker build -t monami-pitch ./backend
```

## 6. Contratos y revisión posterior al despliegue

- `GET /health/live`: proceso activo, sin requerir la base.
- `GET /health/ready`: en pitch devuelve `{"status":"pitch","storage":"postgresql"}` solo con
  esquema y escenario disponibles. Un fallo de base responde `503` sin credenciales.
- `POST /api/v1/pitch/login`: sin cuerpo ni clave, crea una sesión pública y devuelve token opaco
  y vencimiento. Se conserva la ruta para el contrato del pitch.
- `POST /api/v1/pitch/logout`: Bearer token, revoca sesión.
- `POST /api/v1/pitch/reset`: Bearer token, `reset_key`, `expected_generation` y
  `confirmation: "REINICIAR"`. Compara la versión bajo bloqueo antes de reemplazar el estado.
- Rutas del recorrido: siguen en `/api/v1/demo/*`, con Bearer token y actor ficticio `X-Demo-Actor`.
  Las mutaciones incluyen `X-Pitch-Generation`; las revisiones individuales también siguen vigentes.

Tras desplegar: entrar, cambiar roles, modificar un pedido y confirmar que persiste tras reiniciar
FastAPI; completar entrega propia y por tercero; restaurar con el presentador; rechazar clave de reinicio errónea,
sesión cerrada, rol incompatible y acciones antiguas; comprobar CORS desde la URL publicada.

Pruebas PostgreSQL: configurar `TEST_DATABASE_URL` en el entorno con una base separada y TLS,
`MONAMI_TEST_DATABASE_CONFIRMED=true`; ejecutar desde `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Las pruebas crean y limpian únicamente sus escenarios `test-pitch-*`. Cubren persistencia entre
instancias, sesiones, reinicio aislado y conflictos entre procesos. Sin esa base, se omiten: no se
consideran verificación real de PostgreSQL. No usar la base del pitch para ejecutar esa suite.
