# Monami · Hito 9: demo de pitch preparada para despliegue

El modo local conserva **React + Vite + TypeScript → FastAPI → memoria temporal**. El modo pitch añade
**FastAPI → PostgreSQL en Supabase**, escenario preparado, acceso compartido y reinicio por presentador.
La [guía de despliegue y configuración](docs/DEPLOYMENT.md) explica variables, carga y opciones de alojamiento.
La URL real de Supabase se configurará después de esta entrega; la conexión remota aún no está verificada. El plan actualizado
está en [docs/PLAN.md](docs/PLAN.md); los requisitos originales siguen en [docs/Monami.md](docs/Monami.md).

Para pitch usar `DEMO_MODE=false` y `PITCH_MODE=true`, migrar con Alembic y cargar mediante
`python -m app.pitch_seed`. No hay carga ni reinicio automático al arrancar. Las instrucciones
de arranque y recorrido siguientes siguen disponibles para la simulación local vacía.

La clave compartida `PITCH_ACCESS_KEY` admite de **8 a 64 caracteres**, para facilitar el acceso
de los espectadores. La clave privada de reinicio `PITCH_RESET_KEY` conserva de **24 a 256 caracteres**;
deben ser distintas. Ambas se configuran solo en el backend. Para cambiarlas en Vercel, seguir la
[guía de actualización de la clave de acceso](docs/DEPLOYMENT.md#cambiar-la-clave-de-acceso-de-un-despliegue-existente).

Verificaciones del hito 9: `npm.cmd run build`, `ruff check`, `ruff format --check` y comprobación
offline del lock aprobados. **249 pruebas aprobadas, 10 de PostgreSQL omitidas**; cubren el escenario,
restauración del agregado, acceso, límites y rechazo de acciones anteriores a un reinicio.
La comprobación HTTP verifica acceso requerido, fallos de base controlados, contratos, CORS y módulos
del frontend. No equivale a probar persistencia real. Continúa una advertencia de deprecación de HTTPX
en Starlette. Quedan pendientes PostgreSQL real, build Docker (daemon inactivo), revisión visual y
publicación; no se aplicaron migraciones remotas ni se cargaron datos en Supabase.

## Arranque local

En una terminal PowerShell, desde `backend/`:

```powershell
# Solo si todavía no existe el archivo local:
if (!(Test-Path .env.local)) { Copy-Item .env.local.example .env.local }
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

En otra terminal, desde `frontend/`:

```powershell
npm.cmd run dev -- --port 5173 --strictPort
```

Abrir **http://localhost:5173**. No hacen falta contraseñas, conexión Supabase, migraciones
ni el cargador `app.seed`. `backend/.env.local` contiene `DEMO_MODE=true`, sin credenciales.
El archivo local tiene prioridad sobre `.env`; las variables del proceso tienen prioridad mayor.
Las configuraciones de PostgreSQL existentes se conservan y no se utilizan en modo demo.
El backend acepta la API simulada únicamente desde direcciones loopback. Usar un solo proceso
y mantener el servidor en `127.0.0.1`, sin publicarlo ni interponer un proxy.

Si es necesario instalar dependencias, desde la raíz:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.cache/uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path (Get-Location) '.tools/python'
uv sync --project backend --python 3.12 --locked
npm.cmd --prefix frontend ci --cache .cache/npm
```

## Recorrido de aceptación

1. Elegir **Cliente de prueba**. La lista empieza vacía.
2. Abrir **Nuevo pedido**, completar contacto, productos y cantidades, dirección e instrucciones.
3. Opcionalmente pulsar el mapa para seleccionar un punto, o ingresar y aplicar coordenadas.
4. Revisar el resumen; volver para corregir datos si es necesario y enviar.
5. Ver el código `MON-...` y el tracker en **Recibido / Pendiente de confirmación**.
6. Recargar la página: el perfil y el pedido siguen disponibles mientras el backend no reinicie.
7. Cambiar al **Segundo cliente**: la lista está vacía y el código del primero no está disponible.
8. Cambiar a **EmpresaTest**: el pedido aparece en **Por confirmar**. Abrir su detalle y comprobar contacto, productos, dirección y mapa.
9. Escribir un motivo, por ejemplo “Completa el número de casa”, y pulsar **Solicitar corrección**. La confirmación queda bloqueada mientras se espera al cliente.
10. Volver al primer cliente, abrir el pedido y pulsar **Corregir mi pedido**. Editar la dirección, revisar y **Enviar corrección**. El código se conserva.
11. Volver a la empresa y revisar los cambios. **Confirmar pedido**; se puede solicitar otra corrección antes de confirmar si todavía falta algo.
12. Programar una **salida futura** y, opcionalmente, la entrega estimada igual o posterior. Los campos usan hora de Guatemala (UTC−6). Pulsar **Guardar fechas**.
13. **Iniciar preparación** y **Marcar listo para salir**. La salida debe estar programada para habilitar este último botón. Comprobar el grupo **Listos para salir** del panel.
14. Volver al cliente: el tracker y las fechas se actualizan; el historial muestra las acciones. Recargar conserva los cambios mientras FastAPI siga activo.
15. Crear otros pedidos y dejarlos listos con el **mismo día de salida**. Para probar cercanía, usar puntos como `14.635, -90.507` y `14.640, -90.510`, con cantidades pequeñas que quepan en el camión.
16. Desde EmpresaTest, abrir **Planificar entregas**. Seleccionar **Camión de prueba 1** y el día de los pedidos. Ver capacidad total, usada y libre.
17. Pulsar **Proponer agrupación por cercanía**. Comprobar el borrador y los pedidos excluidos por capacidad o falta de coordenadas. La propuesta todavía no guarda asignaciones.
18. Añadir o quitar pedidos con las casillas y cambiar el orden con las flechas. Revisar las paradas numeradas y el trazado simulado; los pedidos sin punto admiten selección manual.
19. Pulsar **Guardar asignación**. Comprobar la reserva del camión, la carga y las paradas. Recargar conserva el plan mientras FastAPI siga activo.
20. Volver al cliente: su pedido muestra **Flota propia** y el camión asignado, manteniendo **Listo para salir**.
21. Para probar liberación, volver a planificación, quitar un pedido y guardar. Para moverlo a otro camión, guardar primero su retirada, seleccionar el otro camión y asignarlo allí.
22. Con un camión que conserve su carga guardada, abrir **EmpresaTest → Viajes**. Seleccionar el camión y **Conductor de prueba**, y pulsar **Asignar viaje al conductor**.
23. Cambiar al perfil **Conductor de prueba**. Revisar productos, cantidades, contactos, direcciones, referencias, mapa y orden de las paradas.
24. Pulsar **Confirmar carga revisada** y después **Iniciar viaje**. La demo permite ensayar la salida aunque la fecha programada sea futura.
25. Pulsar **Simular avance +25%**. Comprobar el porcentaje y el marcador azul en el mapa. Mantenerlo por debajo del 100% para probar un incidente de ruta.
26. Volver a **EmpresaTest → Viajes** y al cliente propietario: ven el mismo avance del vehículo; los pedidos pasan a **En camino** con su salida registrada. El cliente ve su destino sin recibir el manifiesto de otros pedidos.
27. Elegir **Segundo conductor**: no puede consultar ni operar el viaje del primero. Puede recibir otro camión mediante la empresa.
28. Para comprobar ajustes previos a salir, crear otro viaje y usar **Liberar viaje antes de salir** desde empresa. Se libera el conductor y se desbloquea el plan, conservando la carga en el camión.
29. En un viaje en camino, desde conductor o empresa, registrar un **Bloqueo** o **Accidente** con motivo. El avance queda pausado; el cliente ve una alerta general sin datos de otras paradas.
30. Desde **EmpresaTest → Viajes**, previsualizar la alternativa. Comparar el recorrido actual con el desvío naranja; todavía no cambia el viaje. Ingresar minutos de demora y una nota, y aprobar. También se puede resolver continuando el recorrido actual.
31. Comprobar que el porcentaje y la posición no saltaron al aprobar. El conductor puede avanzar nuevamente; empresa y cliente reciben las estimaciones actualizadas. La alternativa es geométrica y ficticia.
32. Desde conductor, marcar un pedido **Con problema**, por ejemplo “Destinatario ausente”. Ver el intento pendiente y su motivo desde empresa y cliente. Este problema individual no pausa el vehículo.
33. Desde empresa, en la parada afectada, completar una nueva salida futura, entrega estimada opcional y nota de resolución. Reprogramar conserva el código y los productos y deja el pedido **Listo para salir**, sin camión ni conductor, para volver a planificarlo.
34. Revisar el historial del cliente y el manifiesto anterior: conservan el intento y las fechas. Planificar el pedido en otro viaje y comprobar que avanzar el viaje anterior no lo modifica.
35. Si se reprograman todos los pedidos de un viaje, este queda archivado como **Reprogramado** y libera camión y conductor. Esto no registra entregas; cada pedido conserva su reprogramación.
36. Crear otro pedido y dejarlo listo, sin camión. Para ensayar falta de capacidad, usar una cantidad de **61 unidades**: supera los tres camiones de prueba.
37. Desde **EmpresaTest → Entrega por tercero**, revisar los aliados ficticios y sus contactos. El filtro **Solo sin camión compatible** identifica pedidos excluidos por capacidad, día o reservas. La cobertura geográfica se revisa manualmente.
38. En el pedido, elegir **PaqueteríaTest** o **EnvíosTest**, indicar por qué no lo cubre la flota y pulsar **Simular solicitud de servicio**. Aparece **Pendiente de aceptación**, manteniendo el pedido **Listo para salir**.
39. Usar **Copiar contacto** o **Copiar solicitud** para ensayar la coordinación: solo copia texto; no se envía correo ni se contacta al aliado. Los correos terminan en `.test`.
40. Cambiar al cliente propietario: conserva código, etapas y fechas y ve **Entrega por tercero**, el nombre del aliado y el estado del servicio. El otro cliente no puede consultar ese pedido.
41. Volver a empresa y pulsar **Simular aceptación del aliado**. El servicio queda confirmado, todavía sin salida registrada. Después usar **Simular despacho por tercero**: el pedido pasa a **En camino** y registra la salida.
42. Pulsar **Simular avance +25%**. El cliente ve el mismo avance manual, sin inventar GPS ni itinerario del aliado. Al 100% sigue pendiente una confirmación explícita de entrega.
43. Para probar cancelación, preparar otro pedido pequeño y solicitar un aliado. Antes del despacho, escribir una nota y **Cancelar servicio antes del despacho**. Conserva el servicio cancelado en el historial y vuelve a estar disponible para flota o para otro aliado.
44. En un viaje propio en camino y sin incidente abierto, desde conductor, elegir un pedido pendiente, escribir una nota opcional y **Confirmar pedido entregado**. No hace falta llegar al 100% para ensayar. Ver su fecha en el manifiesto.
45. Cambiar a empresa: aparece en **Pedidos → Entregados**. El cliente propietario ve la última etapa resaltada, **Pedido entregado**, fecha, autor y nota. Su seguimiento deja de cambiar aunque el vehículo siga con otros pedidos.
46. Confirmar las otras entregas del viaje o reprogramar los pedidos con problema. Cuando no queden pendientes, el viaje aparece **Completado** si tuvo alguna entrega, o **Reprogramado** si todos se reprogramaron. Ver fecha de cierre y manifiesto en empresa y **Mis viajes cerrados** del conductor.
47. Revisar planificación: camión sin carga ni viaje, conductor disponible para una nueva asignación. Preparar otro pedido y comprobar que ambos se pueden reutilizar sin modificar el viaje cerrado.
48. Desde **EmpresaTest → Entrega por tercero**, en un servicio despachado, añadir nota opcional y pulsar **Confirmar entrega por tercero (simulada)**. Empresa registra esta confirmación; no se consulta al aliado. Ver el servicio entre **Entregas por tercero cerradas** y el pedido en **Entregados**.
49. Volver al cliente propietario: conserva su código, aliado e historial y ve fecha y confirmación de entrega. El segundo cliente no puede consultarlo. Recargar conserva el resultado mientras FastAPI siga activo.
50. Ensayar el recorrido completo con dos pedidos: entregar uno por flota, marcar el otro con problema, reprogramarlo y enviarlo por aliado; confirmar su entrega desde empresa. Verificar los dos cierres, el historial del intento y los recursos liberados.

Reglas y límites propuestos para el hito 8:

- El conductor asignado confirma pedidos de su viaje en camino; empresa simula únicamente la entrega
  de un servicio externo ya despachado. No se permite confirmar antes de salir ni por un actor ajeno.
- Transición explícita `en_camino → entregado`, con fecha UTC generada por FastAPI, autor y nota
  opcional de hasta 1000 caracteres. No se admiten fechas o autores enviados por el navegador.
- No se exige el 100% ni validar proximidad al destino: porcentaje y geometría son simulados.
  El porcentaje tampoco entrega pedidos automáticamente ni se fuerza al 100% al cerrar.
- Un incidente de ruta abierto bloquea la confirmación. Un pedido con problema debe reprogramarse
  para otro intento; no se oculta el problema marcándolo entregado en ese mismo intento.
- Cada entrega propia libera su carga y sale del recorrido activo, conservando el manifiesto.
  Camión y conductor siguen reservados hasta resolver todos los pedidos del viaje.
- El viaje termina `completado` si hubo alguna entrega y no quedan pedidos pendientes; conserva las
  paradas reprogramadas como historial. Si todos se reprograman, termina `reprogramado`.
- El pedido entregado es terminal: no recibe nuevos avances, demoras o incidentes de otras paradas.
  Su seguimiento muestra entrega y fecha sin continuar publicando la ubicación del vehículo.
- El cierre conserva historial y referencias de transporte, pero libera los recursos para otro viaje.
  Se asume disponibilidad inmediata en la demo; no se modelan regreso a bodega ni tiempo de retorno.
- Revisiones de pedido y viaje evitan dobles confirmaciones o conflictos con avance y problemas.
  No hay reapertura, entregas parciales, firma, foto, comprobante documental o avisos externos.

Reglas y límites propuestos para el hito 7:

- Dos aliados ficticios con contactos de prueba. Sin registro de aliados, tarifas, cotizaciones,
  mensajería, aceptación externa, API de paqueterías ni seguimiento real.
- Solo pedidos listos, con fecha de salida y sin camión, viaje o servicio activo. Retirar primero
  la asignación de flota; si hay viaje, liberarlo antes de salir. Un pedido en camino no cambia de transporte.
- La evaluación de flota considera capacidad restante, día y bloqueo por viaje. No garantiza disponibilidad
  de conductor, cobertura geográfica o aceptación del aliado. Empresa puede elegir tercero aunque haya
  capacidad compatible, pero debe registrar el motivo operativo.
- Solicitud y aceptación conservan `listo_para_salir`; solo el despacho simulado cambia a `en_camino`.
  La empresa opera los tres pasos. El aliado no tiene un nuevo rol ni una sesión de acceso.
- Se puede cancelar con motivo antes del despacho y volver a planificar el mismo pedido; se conserva
  la referencia y el historial del servicio anterior. No hay cancelación ni reprogramación de servicios
  ya despachados por tercero en este hito; esa política queda pendiente.
- Fechas bloqueadas mientras haya un servicio activo: cancelarlo antes de ajustar y solicitar de nuevo.
  El despacho simulado puede adelantarse a la salida programada para ensayar, como en flota propia.
- Un servicio activo excluye el pedido de sugerencias y asignación a camiones. Las revisiones impiden
  aplicar dos asignaciones o decisiones incompatibles simultáneas. El pedido conserva identidad e historial.
- El avance es manual, en pasos del 25%, sin GPS, mapa de ruta externa ni entrega automática al 100%.

Reglas y límites propuestos para el hito 6:

- Solo un incidente de ruta abierto por viaje, en camino y antes del 100%. Empresa o conductor
  asignado lo reportan; solo empresa decide cómo continuar. No hay avance mientras siga abierto.
- El desvío requiere coordenadas completas. Sin ellas, se puede resolver con **Continuar recorrido actual**.
  La propuesta no consulta carreteras ni valida transitabilidad y solo se aplica al aprobarla.
- La demora manual, de 0 a 1440 minutos, se suma a la estimación vigente o a la hora actual si
  aquella falta o ya pasó. Es una estimación simulada, no un cálculo de duración del recorrido.
- El conductor registra el intento fallido; la empresa reprograma el mismo pedido. Se guarda motivo,
  autor, fechas e historial. La nueva salida usa hora de Guatemala y debe ser futura al guardarla.
- La reprogramación permite la excepción `en_camino → listo_para_salir`. Retira el pedido del viaje
  activo y libera su capacidad; el manifiesto original permanece como historial. Se asume disponibilidad
  inmediata de esa carga para la simulación; no se modela su retorno físico a bodega.
- Cambios simultáneos comprueban las revisiones de viaje y pedido; una operación obsoleta devuelve
  `409` sin cambios parciales. El cliente solo recibe información de su propio pedido.

Reglas y límites del hito 5:

- La empresa elige entre dos conductores ficticios; cada uno puede tener un único viaje activo.
- El manifiesto queda fijado al asignarlo. Para cambiar carga o fechas, liberar primero el viaje
  desde empresa. La liberación solo se admite antes de iniciar; no cancela los pedidos.
- La carga debe confirmarse antes de salir. El inicio cambia todos sus pedidos a **En camino**
  y guarda la salida real. La fecha programada más temprana es una referencia; en la simulación
  se permite iniciar antes de esa fecha para ensayar sin esperar.
- El avance se controla manualmente en pasos del 25%. Con todas las coordenadas, la posición
  se interpola sobre el trazado geométrico de las paradas; sin ellas no se estima posición tras el inicio.
- El porcentaje representa el recorrido del vehículo, sin confirmar entregas individuales.
  Al 100% los pedidos sin confirmar siguen en **En camino**. El cierre requiere resolver sus entregas.
- Los contactos y el manifiesto completo se muestran solo a empresa y al conductor asignado.
  El cliente recibe su propio destino y la posición simulada compartida del vehículo. Su línea en el
  mapa es una referencia bodega–destino, no el itinerario completo.
- Las estimaciones se conservan hasta una decisión explícita de empresa; el hito 6 añade incidentes,
  alternativas de ruta y reprogramación. No hay GPS real, despacho por reloj ni movimiento automático.

Reglas y límites propuestos para el hito 4:

- Camiones ficticios de **20, 40 y 60 unidades**. La carga es la suma de las cantidades solicitadas;
  peso, volumen y empaquetado se definirán después.
- Un plan por camión, para un solo día de salida de Guatemala. Vaciar y guardar libera el camión
  para otro día. Si un pedido ya está asignado, retirarlo del camión antes de cambiar su día de salida.
- La sugerencia conserva las paradas guardadas y agrega pedidos por cercanía geométrica que caben.
  Los pedidos sin coordenadas quedan fuera de la propuesta automática, pero admiten asignación manual.
- La empresa confirma la lista completa y puede ajustar su orden. Una asignación rechazada conserva
  la carga anterior. Se impiden sobrecapacidad, pedidos duplicados y reservas en dos camiones.
- Las vistas se actualizan cada cinco segundos. Si cambió la planificación mientras editabas,
  actualizar y usar **Descartar borrador y cargar plan actual** antes de revisar y guardar de nuevo.
- Los borradores se descartan al cambiar de camión o salir; las asignaciones guardadas persisten
  hasta reiniciar FastAPI. No se produce despacho automático.

También se pueden abrir dos pestañas con roles distintos: las vistas consultan cambios cada cinco segundos
y tienen un botón para actualizar. En esta simulación solo existe EmpresaTest. Los pedidos confirmados
pendientes de iniciar preparación y los que ya se preparan comparten el grupo **En preparación**,
con su estado específico visible. **En camino** se actualiza al iniciar un viaje o despachar por tercero.
**Entregados** muestra las confirmaciones de conductor o empresa, con su fecha. El conductor consulta
su viaje activo y el historial de sus propios viajes cerrados.

Los datos empiezan vacíos y se borran al reiniciar FastAPI, incluso por recarga automática de código.
Por eso el comando de demo no lleva `--reload`. Los perfiles seleccionables son actores de simulación,
no cuentas persistidas ni autenticación. Solo se guarda su identificador en `sessionStorage`.
Las fechas aparecen al programarlas; asignar un camión identifica el transporte como flota propia.
El tracker avanza mediante acciones de empresa y conductor y llega a **Entregado** con confirmación explícita.

Las decisiones de esta implementación están descritas en [docs/PLAN.md](docs/PLAN.md): correcciones
dentro de “Recibido”, edición solo a petición de empresa antes de confirmar, salida obligatoria para
marcar listo y entrega estimada opcional. Son propuestas para la demo; los requisitos originales
no especifican todas estas reglas. Si una operación falla por un cambio simultáneo (`409`),
actualizar y revisar el detalle antes de repetirla. En una corrección, volver al detalle y reabrir
el formulario para cargar la versión actual.

El mapa usa Leaflet, añadido para marcar coordenadas, y cartografía de OpenStreetMap con atribución.
La cartografía necesita Internet; sin conexión se puede usar la dirección e ingresar coordenadas
manualmente. El mapa de planificación muestra una bodega ficticia, paradas numeradas y líneas
discontinuas entre puntos conocidos. Se dejan espacios donde faltan coordenadas. La distancia mostrada
es geométrica desde la bodega, sin retorno; no hay cálculo de carreteras, navegación, GPS ni geocodificación.
Referencias:
[Leaflet](https://leafletjs.com/examples/quick-start/) y [uso de cartografía OSM](https://operations.osmfoundation.org/policies/tiles/).

## Contratos simulados

Solo se registran con `DEMO_MODE=true`:

| Ruta | Comportamiento |
| --- | --- |
| `GET /health/ready` | `200 {"status":"demo","storage":"memory"}`; no comprueba PostgreSQL |
| `GET /api/v1/demo/context` | EmpresaTest y actores seleccionables |
| `POST /api/v1/demo/orders` | Crea pedido en estado `recibido`; devuelve código, fecha y contenido |
| `GET /api/v1/demo/orders` | Pedidos del cliente seleccionado |
| `GET /api/v1/demo/orders/{code}` | Detalle y seguimiento; ajeno/inexistente devuelve `404` |
| `POST /api/v1/demo/orders/{code}/correction` | Cliente propietario reenvía datos cuando existe corrección pendiente |
| `GET /api/v1/demo/company/orders` | Empresa consulta todos los pedidos de EmpresaTest |
| `GET /api/v1/demo/company/orders/{code}` | Detalle completo para empresa |
| `POST /api/v1/demo/company/orders/{code}/actions` | Confirmar, solicitar corrección, preparar o marcar listo |
| `POST /api/v1/demo/company/orders/{code}/schedule` | Programar o ajustar salida y entrega estimada |
| `GET /api/v1/demo/company/planning` | Revisión de planificación, bodega, camiones, capacidades, paradas y pedidos listos |
| `POST /api/v1/demo/company/trucks/{truck_id}/suggestion` | Propone códigos ordenados por cercanía y capacidad; no asigna |
| `POST /api/v1/demo/company/trucks/{truck_id}/assignment` | Reemplaza la lista ordenada de pedidos de un camión o libera su carga |
| `GET /api/v1/demo/company/trips` | Viajes, conductores disponibles y camiones con carga sin viaje |
| `POST /api/v1/demo/company/trips` | Asigna conductor y fija el manifiesto de un camión |
| `POST /api/v1/demo/company/trips/{trip_id}/cancel` | Libera el viaje antes de salir, manteniendo los pedidos en el camión |
| `GET /api/v1/demo/driver/trip` | Viaje activo del conductor seleccionado, o `null` |
| `GET /api/v1/demo/driver/trips/{trip_id}` | Detalle del viaje propio; otro conductor recibe `404` |
| `GET /api/v1/demo/driver/trips` | Historial de viajes completados o reprogramados del conductor seleccionado |
| `POST /api/v1/demo/driver/trips/{trip_id}/actions` | Confirma carga, inicia viaje o simula avance |
| `GET /api/v1/demo/orders/{code}/tracking` | Seguimiento del vehículo para el cliente propietario, sin otras paradas |
| `POST /api/v1/demo/company/trips/{trip_id}/incidents` | Empresa reporta bloqueo o accidente y pausa el avance |
| `POST /api/v1/demo/driver/trips/{trip_id}/incidents` | Conductor asignado reporta el incidente |
| `POST /api/v1/demo/company/trips/{trip_id}/incidents/{incident_id}/alternative` | Previsualiza un desvío sin guardar cambios |
| `POST /api/v1/demo/company/trips/{trip_id}/incidents/{incident_id}/resolve` | Empresa aprueba alternativa o continúa; actualiza estimaciones |
| `POST /api/v1/demo/driver/trips/{trip_id}/orders/{code}/problem` | Registra un intento fallido del pedido propio del viaje |
| `POST /api/v1/demo/company/orders/{code}/reschedule` | Reprograma el mismo pedido y lo libera para una nueva planificación |
| `GET /api/v1/demo/company/third-party` | Aliados ficticios, pedidos sin transporte y evaluación de flota, servicios activos |
| `POST /api/v1/demo/company/orders/{code}/third-party/request` | Solicita servicio simulado a un aliado y reserva el pedido para tercero |
| `POST /api/v1/demo/company/orders/{code}/third-party/actions` | Simula aceptación, despacho, avance, confirmación de entrega o cancelación previa al despacho |
| `POST /api/v1/demo/driver/trips/{trip_id}/orders/{code}/deliver` | Conductor asignado confirma entrega con revisión de viaje y pedido |

Las rutas de cliente requieren `X-Demo-Actor: cliente-1` o `cliente-2`; las rutas de empresa requieren
`X-Demo-Actor: empresa`. Crear requiere además
`Idempotency-Key`, generado por el frontend para cada envío: repetir el mismo envío devuelve el mismo
pedido; usar esa clave con otros datos devuelve `409`. El backend valida cantidades enteras positivas,
contactos, textos y coordenadas; no acepta que el cliente envíe propietario o estado.
El encabezado de actor permite simular el ámbito de cada cliente, no proporciona seguridad de usuario.
Las lecturas se actualizan cada cinco segundos y admiten reintentos ante fallos de conexión.

Los contratos completos están en **http://127.0.0.1:8000/docs** con FastAPI activo.
Los cambios del hito 3 requieren `expected_revision` con la revisión consultada del pedido.
No se repiten automáticamente las mutaciones: una revisión obsoleta devuelve `409` sin cambios.

Ejemplo de cuerpo (sustituir la revisión por el valor vigente):

```json
{"action":"request_correction","note":"Completa el número de casa","expected_revision":1}
```

Las otras acciones son `confirm`, `start_preparation` y `mark_ready`, con `note` omitido.
El cuerpo para fechas incluye `expected_revision`, `scheduled_departure_at` y `estimated_delivery_at`
opcional o `null`; ambas fechas deben llevar zona horaria, por ejemplo `2030-01-15T09:00:00-06:00`.
El cuerpo para corrección incluye `expected_revision` y `order` con los mismos campos de una nueva solicitud.
Las respuestas añaden `revision`, `correction_status`, `correction_note` e `history`.

La planificación tiene una revisión global distinta de la revisión individual del pedido.
Usar el `revision` de `GET /api/v1/demo/company/planning` como `expected_revision` para sugerir o asignar.
La sugerencia requiere además `departure_date` (`YYYY-MM-DD`). La asignación requiere esa fecha y
`order_codes` en orden de parada (máximo 100); para liberar, enviar `order_codes: []` y
`departure_date: null`. Una asignación idéntica con revisión actual no repite historial.
Los pedidos añaden `assigned_truck_id` y `assigned_truck_name`. El cliente no recibe la lista de otros pedidos.

Crear viaje requiere `truck_id`, `driver_id` (`conductor` o `conductor-2`) y `expected_revision`
con la revisión global de planificación, también publicada por `GET /api/v1/demo/company/trips`.
Las acciones usan `X-Demo-Actor` del conductor asignado y el cuerpo
`{"action":"confirm_load","expected_revision":1}` con la revisión individual vigente del viaje.
Las otras acciones son `start_trip` y `advance`. Liberar requiere la revisión del viaje y el actor empresa.
Una acción obsoleta devuelve `409` sin repetir historial ni sobrescribir datos.
Los pedidos añaden `trip_id`, `assigned_driver_name` y `actual_departure_at`.

Los incidentes requieren `expected_revision` del viaje, `kind` (`bloqueo` o `accidente`) y `reason`.
La previsualización recibe solo esa revisión. Resolver requiere además `decision` (`alternativa` o
`continuar`), `delay_minutes` entero de 0 a 1440 y `resolution_note` no vacía.
Registrar un problema requiere la revisión del viaje, `expected_order_revision` y `reason`.
Reprogramar requiere `expected_revision` del pedido, `expected_trip_revision`, nueva
`scheduled_departure_at`, `estimated_delivery_at` opcional y `resolution_note`. Las fechas llevan zona
horaria; la entrega no puede ser anterior a la salida. Los pedidos incluyen `needs_reschedule` y
`delivery_attempts`; los viajes conservan `incidents` y las paradas excluidas por reprogramación.

Solicitar tercero requiere `expected_revision` del pedido, `partner_id` (`aliado-1` o `aliado-2`) y
`reason` no vacío. Las acciones requieren la revisión actual, `action` (`confirm`, `dispatch`,
`advance`, `cancel` o `deliver`) y `note` opcional, obligatoria al cancelar. Todo lo opera el actor empresa.
Un conflicto devuelve `409` sin cambios parciales; no se reintentan mutaciones automáticamente.
El pedido incorpora `third_party` con aliado, referencia, estado, fechas, porcentaje e historial;
`third_party_history` conserva servicios cancelados. El seguimiento propio devuelve modo tercero,
aliado, referencia y porcentaje sin publicar otros pedidos ni inventar posición.

Confirmar entrega propia requiere `expected_revision` del viaje, `expected_order_revision` de la
parada y `note` opcional. El pedido devuelve `status: entregado`, `delivered_at`, `delivered_by`
y `delivery_note`; el viaje añade `completed_order_codes`, resultados por parada y `closed_at`.
Confirmar tercero usa la acción `deliver` con la revisión del pedido. La fecha se comparte entre
pedido y servicio. El endpoint de seguimiento devuelve `status: entregado` y `delivered_at`, sin GPS.
El viaje completo usa `completado`; su porcentaje conserva el valor simulado al cerrar.

## Verificaciones del hito 8

Desde `frontend/`: `npm.cmd run build`.
Desde `backend/`:

```powershell
.\.venv\Scripts\ruff.exe check app tests migrations
.\.venv\Scripts\ruff.exe format --check app tests migrations
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Resultado: **230 pruebas aprobadas, 6 de PostgreSQL omitidas** por falta de una base de pruebas.
Cubren creación y lectura, aislamiento de clientes, roles simulados, correcciones y reenvío,
transiciones de preparación, fechas y zonas horarias, revisiones obsoletas, concurrencia, historial,
reservas y liberación de camiones, capacidad, sugerencias por cercanía, días de Guatemala,
reordenación, asignaciones simultáneas, aislamiento de los datos del cliente, reinicio de memoria,
desactivación del modo demo y rechazo de clientes remotos. Además: manifiestos, asignación de conductor,
confirmación de carga, inicio y avance del viaje, privacidad del seguimiento, liberación previa a salida,
aislamiento entre conductores y conflictos entre liberar e iniciar. El hito 6 añade pausa por incidente,
previsualización sin mutaciones, continuidad de posición al aprobar desvíos, demoras acumuladas,
reprogramaciones parciales y totales, historial de múltiples intentos y conflictos entre avanzar y
reprogramar. El hito 7 añade evaluación de capacidad y reservas, solicitud y aceptación de servicio,
despacho, avance manual, cancelación con historial, exclusión entre flota y aliado, seguimiento propio,
reprogramación de flota seguida de tercero y decisiones concurrentes sin doble asignación.
El hito 8 cubre entregas antes o después del 100%, cierre total o mixto con reprogramación,
liberación y reutilización de recursos, historial propio del conductor, seguimiento final congelado,
confirmación de tercero por empresa, rechazo de actores ajenos, datos falsificados y dobles envíos.
Continúa la advertencia de deprecación de HTTPX en Starlette. En este entorno de Windows fue
necesario ejecutar pytest fuera del aislamiento para permitir el socket local que necesita asyncio.
La compilación TypeScript/Vite y la comprobación HTTP con ambos servidores también pasaron
(dos clientes, corrección, preparación, viaje propio, incidente y alternativa, entrega propia,
problema y reprogramación, cierre mixto, tercero confirmado por empresa, fechas finales,
privacidad, recursos liberados, CORS y módulos de Vite). Esta comprobación usó un backend
temporal aislado, detenido al terminar.
La revisión visual está aplazada por el usuario; las verificaciones anteriores comprueban código y API.

## Referencia histórica de infraestructura del hito 1 (modo identidad)

Para usar solo identidad del hito 1, configurar `DEMO_MODE=false` y `PITCH_MODE=false` y reiniciar FastAPI.
Ese modo conserva únicamente el acceso e identidad del hito 1; los pedidos persistidos aún están pendientes.
Las instrucciones siguientes quedan como referencia futura, no son requisitos para ejecutar la simulación.

Base de acceso y contratos iniciales. Requisitos funcionales: [docs/Monami.md](docs/Monami.md).

**React + Vite + TypeScript → FastAPI → PostgreSQL gestionado por Supabase.**

React solo llama a FastAPI. El backend autentica, aplica permisos y accede a datos.
No hay cliente Supabase en el frontend, registro público ni funcionalidad de pedidos persistidos en este modo.

## Estructura y dependencias

- `frontend/`: React y React DOM para la interfaz; Vite y su plugin React para desarrollo y build;
  TypeScript y tipos React para validación estática.
- `backend/app/`: FastAPI, servido por Uvicorn; SQLAlchemy y Psycopg para PostgreSQL;
  Pydantic Settings para configuración; Argon2 para hashes de contraseñas.
- `backend/migrations/`: Alembic para cambios explícitos de esquema.
- `backend/tests/`: pytest y HTTPX para API e integración; Ruff para análisis y formato.

Las versiones resueltas quedan en `frontend/package-lock.json` y `backend/uv.lock`.
Se requiere Node >=22.12, Python 3.12 o 3.13 y uv. Aquí se verificó con Node 24 y Python 3.12.

## Instalación local (PowerShell)

Desde la raíz del proyecto, se pueden mantener las herramientas y cachés dentro del workspace:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.cache/uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path (Get-Location) '.tools/python'
uv sync --project backend --python 3.12 --locked
npm.cmd --prefix frontend ci --cache .cache/npm
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env
```

Editar `backend/.env` localmente con los valores reales, fuera del código y de Git.
No es necesario cambiar la política de ejecución de PowerShell: usar `npm.cmd`.

## Base de datos y secretos

| Variable del backend | Uso |
| --- | --- |
| `DATABASE_URL` | Conexión de la aplicación con usuario de permisos limitados |
| `MIGRATION_DATABASE_URL` | Opcional: cuenta de migraciones con permisos DDL; solo la utiliza Alembic |
| `CORS_ORIGINS` | Lista JSON de orígenes exactos del frontend, sin rutas ni comodines |
| `SESSION_TTL_MINUTES` | Duración de sesión: 480 minutos por defecto, máximo 1440 |
| `DEMO_CLIENT_PASSWORD`, `DEMO_COMPANY_PASSWORD`, `DEMO_DRIVER_PASSWORD` | Tres contraseñas de 12 a 1024 caracteres para la carga explícita |

Copiar la conexión desde Supabase **Connect**. Usar el esquema de controlador
`postgresql+psycopg://` y `sslmode=require`, `verify-ca` o `verify-full`.
Codificar los caracteres reservados de usuario/contraseña en la URL. Nunca poner esta URL en
una variable `VITE_*`, en el navegador ni en el repositorio.

La conexión directa o por pooler se elegirá al definir el alojamiento de FastAPI. El driver
deshabilita prepared statements para ser compatible con un pooler transaccional. Las migraciones
deben usar una conexión directa o de sesión, con permisos DDL. Consultar la
[guía oficial de conexiones de Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres).

Las tres tablas funcionales (`organizations`, `users`, `sessions`) están en el esquema privado
`monami`, separado de `public`. No agregar `monami` a los esquemas expuestos por las APIs de
Supabase ni otorgar acceso a roles del navegador. Las reglas por organización se aplican en
FastAPI; no se depende de Supabase Auth, RLS ni Data API para este hito.
Alembic mantiene su tabla técnica `public.monami_schema_version`.

Después de provisionar las cuentas de base y ejecutar la migración con la cuenta DDL,
otorgar a la cuenta de aplicación únicamente los permisos necesarios. Ejemplo, reemplazando
`monami_app` por el rol real (su creación y contraseña se gestionan fuera del repositorio):

```sql
GRANT USAGE ON SCHEMA monami TO monami_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA monami TO monami_app;
GRANT SELECT ON public.monami_schema_version TO monami_app;
```

La cuenta de aplicación no necesita ser propietaria del esquema ni tener permisos DDL.
Revisar los permisos al incorporar futuras migraciones.

## Migración y cuentas de demostración

Desde `backend/`, con la configuración cargada en `.env` o en el entorno:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.seed
```

Estos pasos son explícitos: arrancar FastAPI **no crea tablas ni carga usuarios**.
La carga es idempotente y no reemplaza contraseñas existentes.

| Cuenta | Rol |
| --- | --- |
| `cliente@monami.test` | cliente |
| `empresa@monami.test` | empresa |
| `conductor@monami.test` | conductor |

Las tres cuentas pertenecen a `Monami Demo`. No existen contraseñas predeterminadas.

## Arranque

En una terminal, desde `backend/`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

En otra, desde `frontend/`:

```powershell
npm.cmd run dev
```

Abrir `http://localhost:5173`. La configuración de ejemplo del frontend apunta a
`http://127.0.0.1:8000`. FastAPI publica `/docs` y `/openapi.json`.
La sesión solo vive en memoria del frontend; recargar requiere iniciar sesión nuevamente.
Cerrar sesión revoca el token en el servidor. Las contraseñas se guardan como Argon2id y los
tokens opacos únicamente como hashes SHA-256, con vencimiento controlado por el backend.

Sin `DATABASE_URL`, la API puede arrancar y publicar contratos, pero readiness y las operaciones
de datos devuelven `503`; esto no equivale a una demo conectada y lista.

## Contratos iniciales

| Método y ruta | Comportamiento |
| --- | --- |
| `GET /health/live` | `200 {"status":"ok"}`, independiente de PostgreSQL |
| `GET /health/ready` | `200 {"status":"ready"}` si la revisión, tablas y permisos SELECT son correctos; de lo contrario `503` |
| `POST /api/v1/auth/login` | JSON `{email,password}`; retorna `{access_token,token_type,expires_at}` |
| `POST /api/v1/auth/logout` | Bearer token; revoca sesión, retorna `204` |
| `GET /api/v1/me` | Bearer token; retorna identidad, rol y organización de la sesión |
| `GET /api/v1/company` | Bearer token y rol empresa; retorna exclusivamente su organización |

UUID y fechas UTC se serializan como cadenas. Errores de API usan `{ "detail": "..." }`:
`401` para autenticación, `403` para permisos, `422` para entrada inválida y `503` para fallos
de datos. Las respuestas y errores no incluyen contraseñas, hashes ni conexiones.
El frontend envía `Authorization: Bearer ...`; no se utilizan cookies de autenticación.

## Verificaciones

Desde `frontend/`:

```powershell
npm.cmd run build
```

Desde `backend/`:

```powershell
.\.venv\Scripts\ruff.exe check app tests migrations
.\.venv\Scripts\ruff.exe format --check app tests migrations
.\.venv\Scripts\python.exe -m pytest -q
```

Las pruebas unitarias no requieren PostgreSQL y no usan SQLite como sustituto.
Para ejecutar también las seis pruebas de integración, configurar **en el entorno del proceso**
`TEST_DATABASE_URL` con una base PostgreSQL separada y TLS, y
`MONAMI_TEST_DATABASE_CONFIRMED=true`. No usar la base de la demo ni una base de otro proyecto.
La confirmación exige verificar manualmente que se trata de un destino separado, incluso si
se accede por distintos endpoints o poolers. La suite también rechaza destinos coincidentes
por host/puerto/base con `DATABASE_URL`.

La integración aplica `upgrade head` dos veces, comprueba login/logout, hash de tokens,
expiración, usuarios desactivados, roles, aislamiento entre dos organizaciones e idempotencia
de la carga demo. Limpia únicamente sus filas; conserva las migraciones. Sin conexión de prueba,
estos casos se reportan como omitidos, no como aprobados.

## Límites y pendientes

- Validar conexión, migraciones y permisos con la instancia Supabase real y una base de pruebas.
- Elegir alojamiento independiente para React y FastAPI, orígenes HTTPS y modalidad de conexión.
- PostGIS sigue pendiente hasta definir mapas y consultas por cercanía.
- Este hito no incluye pedidos, registro público, recuperación de contraseña, Refine ni despliegue.
- Antes de exponer el acceso públicamente, concretar controles de acceso del despliegue y límites
  de intentos de autenticación.

El siguiente hito requiere revisión de este resultado antes de comenzar.

## Resultado histórico de la verificación del hito 1

- `npm.cmd run build`: TypeScript y build de producción aprobados.
- `ruff check` y `ruff format --check`: aprobados.
- `python -m pytest -q`: 22 aprobadas, 6 omitidas por falta de `TEST_DATABASE_URL`.
  Incluye generación offline del SQL inicial; no equivale a aplicar la migración en PostgreSQL.
- Smoke HTTP con Uvicorn y Vite preview: frontend `200`, liveness `200` y login sin base `503`
  con mensaje controlado y CORS del origen configurado.
- Instalación npm: auditoría sin vulnerabilidades reportadas.
- La versión instalada de Starlette emite una advertencia de deprecación de HTTPX en TestClient;
  no impide las pruebas. Se conserva HTTPX conforme al plan aprobado.
- La comprobación visual queda pendiente: no había un navegador conectado.
- No se conectó a Supabase, no se aplicaron migraciones remotas ni se cargaron cuentas reales.
