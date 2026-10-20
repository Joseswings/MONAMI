# Monami: plan actualizado para MVP simulado

Fuente funcional: [Monami.md](Monami.md). Cambio aprobado: priorizar el recorrido local simulado
y aplazar Supabase y el alta de usuarios hasta revisar el MVP.

## Decisiones confirmadas

- React + Vite + TypeScript consumen FastAPI. Refine permanece pendiente.
- Durante la simulación, FastAPI aplica validación y reglas de pedidos y conserva el estado en memoria.
- Sin registro ni contraseñas en la simulación: se selecciona un actor/rol de prueba.
- La demo comienza sin pedidos; reiniciar el backend reinicia los datos.
- El modo simulado es local, de un solo proceso. Su selección de actores no es autenticación.
- PostgreSQL en Supabase sigue siendo la persistencia futura; las credenciales pertenecen al backend.
- PostGIS, GPS real, optimización de rutas e integraciones de aliados siguen pendientes.

## Hitos

1. Base del proyecto y contratos: infraestructura de frontend/backend, identidad y migraciones preparadas.
2. Pedido del cliente, en simulación: contacto, productos, cantidades, dirección y punto opcional,
   resumen editable, envío, código, lista propia y tracker inicial. Se valida recarga del navegador,
   aislamiento de actores, entradas inválidas y reintentos sin duplicar. Revisado y aceptado.
3. Empresa: revisión, confirmación, solicitud y resolución de correcciones, fechas y preparación.
   Implementado; revisión visual aplazada por el usuario.
4. Planificación: camiones, capacidades, sugerencias de agrupación y asignaciones ajustables.
   Revisado y aceptado por el usuario.
5. Viaje del conductor: carga, productos, contactos, mapa, paradas y avance compartido.
   Revisado y aceptado por el usuario; recorrido detallado en README.md.
6. Incidentes y reprogramación: problemas, alternativa de ruta, nuevas estimaciones e historial de intentos.
   Revisado y aceptado por el usuario.
7. Aliados: contacto, solicitud y aceptación de servicio, despacho y seguimiento por tercero.
   Revisado y aceptado por el usuario.
8. Cierre y ensayo: registrar entrega, fecha y seguimiento actualizado entre los tres roles.
   Implementado para revisión. Empresa simula la confirmación de entregas por tercero, aprobado por el usuario.
   No se inicia la integración del hito 9 hasta revisar este resultado.
9. Demo desplegable para pitch: escenario ficticio preparado y reiniciable, persistencia PostgreSQL
   en Supabase, acceso compartido y reinicio por presentador, despliegues separados de React y FastAPI.
   Código preparado; conexión real, integración PostgreSQL y publicación pendientes de configuración.
   El alta de empresa y usuarios reales y los permisos de una aplicación productiva quedan fuera del pitch.

Cada hito requiere revisión antes de iniciar el siguiente. El hito 5 permite iniciar el viaje y
mover pedidos a `en_camino`. Los incidentes y la confirmación de entrega conservan sus hitos.
El pedido avanza solo mediante acciones explícitas de los actores.

## Propuestas de implementación del hito 2

- EmpresaTest y dos clientes seleccionables para comprobar el ámbito de consulta, sin cuentas en base.
- Productos escritos manualmente, sin catálogo, precios ni inventario.
- Coordenadas mediante Leaflet con OpenStreetMap; dirección y coordenadas manuales disponibles sin tiles.
- FastAPI genera identificador y fecha; frontend muestra las seis etapas, manteniendo la actual en recibido.
- Las fechas y el transporte permanecen sin asignar hasta los hitos operativos.
- La API de simulación se habilita explícitamente mediante `DEMO_MODE=true`; no sustituye la API persistida.

## Hito 3: requisitos y decisiones de implementación

Requisitos de Monami.md: la empresa consulta órdenes y detalles, confirma o solicita correcciones,
registra la salida y actualiza la preparación. El panel organiza pedidos por confirmar, en preparación,
listos, en camino y entregados. El cliente conoce qué corregir, la etapa y las fechas disponibles.

Decisiones propuestas para esta simulación, pendientes de revisión del hito:

- Una sola empresa, EmpresaTest, revisa pedidos de ambos clientes simulados.
- Las correcciones son un indicador adicional dentro de `recibido`, conservando las seis etapas
  del tracker. Se registra motivo, autor y fecha en el historial.
- Solo se solicitan correcciones antes de confirmar. El cliente propietario modifica y reenvía
  el mismo pedido; la empresa revisa, puede pedir otra corrección y confirma para resolverla.
- No se confirma mientras se espera respuesta del cliente, ni se edita un pedido confirmado.
- Transiciones: `recibido → confirmado → preparando → listo_para_salir`. Sin saltos ni retrocesos.
- Después de confirmar se programa o ajusta la salida y, opcionalmente, la entrega estimada.
  La salida debe ser futura al guardarla y la entrega igual o posterior. Se admite dejar la estimación pendiente.
- Para marcar listo se exige salida programada. No se exige camión todavía.
- El formulario usa hora de Guatemala (UTC−6); FastAPI recibe fechas con zona y las conserva en UTC.
- Cada cambio valida la revisión del pedido. Un envío obsoleto responde `409`, sin sobrescribir
  información ni duplicar el historial. La vista se actualiza cada cinco segundos o manualmente.
- La lista agrupa confirmados pendientes de preparar y pedidos en preparación bajo “En preparación”,
  mostrando el estado específico de cada uno. En camino y entregados permanecen vacíos hasta sus hitos.
- Historial y pedidos se conservan en memoria y se reinician con FastAPI.

Criterios de aceptación: completar revisión, solicitud de corrección, reenvío del cliente, confirmación,
fechas, preparación y listo con el mismo código; ver los cambios desde el cliente; rechazar actores
incompatibles, correcciones ajenas, saltos, fechas inválidas y envíos obsoletos. Compilación y pruebas
automáticas aprobadas; revisión visual manual pendiente.

## Hito 4: requisitos y decisiones de implementación

Requisitos de Monami.md: mostrar pedidos listos y camiones disponibles con su capacidad; consultar
la carga y el recorrido por camión; proponer agrupaciones por cercanía y capacidad; permitir ajustes
y actualizar la disponibilidad al asignar pedidos.

Decisiones propuestas para esta simulación, pendientes de revisión del hito:

- Tres camiones ficticios (`camion-1`, `camion-2`, `camion-3`) de 20, 40 y 60 unidades. No se precargan pedidos.
- Carga = suma de las cantidades solicitadas. Cada unidad equivale a una unidad de carga simulada;
  todavía no se modelan peso, volumen, bultos ni restricciones por producto.
- Bodega ficticia en Guatemala (14.6349, -90.5069), usada como origen del mapa y de la propuesta.
- Un camión conserva un único plan para un día de salida de Guatemala (UTC−6). No se mezclan días
  y debe liberarse su carga antes de reservarlo para otro día. Las horas de pedidos del mismo día
  se conservan individualmente; no se calculan horarios de ruta ni ventanas de entrega.
- Estados de disponibilidad derivados de la carga: disponible, reservado con espacio, completo.
  Un camión reservado puede recibir más pedidos del mismo día hasta su capacidad.
- La propuesta conserva las paradas ya guardadas y añade el pedido más cercano al último punto,
  repitiendo mientras haya pedidos que quepan. Comienza en la bodega si no hay paradas.
  Es una heurística de distancia geométrica, sin optimización global ni consulta de carreteras.
- Solo se proponen pedidos listos, sin otro camión y con coordenadas. Los pedidos sin coordenadas
  se pueden asignar manualmente y se identifican como tramos incompletos en el mapa. La dirección
  no se geocodifica automáticamente. Los pedidos que no caben se muestran como excluidos.
- La empresa puede añadir, quitar y reordenar paradas en un borrador, y guardar la asignación completa.
  Sugerir y editar el borrador no reservan carga. Cambiar de camión o salir descarta cambios sin guardar.
- Guardar valida el plan completo antes de modificar datos. Se rechazan sobrecapacidad, duplicados,
  pedidos no listos, asignaciones a otro camión, mezcla de días y revisiones obsoletas (`409`).
- Retirar un pedido libera su carga y revierte su transporte a pendiente. Para trasladarlo a otro
  camión, primero se guarda la retirada y después la nueva asignación.
- Una revisión global de planificación invalida borradores cuando cambian pedidos listos, fechas
  o asignaciones. La actualización cada cinco segundos conserva el borrador y avisa del conflicto.
- La asignación marca flota propia en el pedido y registra historial. El cliente recibe únicamente
  los datos de su pedido y el nombre de su camión; el itinerario completo queda en la vista de empresa.
- El mapa numera paradas y une puntos conocidos con líneas discontinuas, sin conectar tramos con
  coordenadas ausentes. La distancia publicada es geométrica desde bodega, sin retorno y sin duración.
- Todo permanece en memoria local, sin dependencias nuevas ni conexión a Supabase. El hito termina
  con pedidos listos y camiones reservados; conductor, despacho y avance de viaje pertenecen al hito 5.

Criterios de aceptación: preparar varios pedidos, obtener una sugerencia, ajustar y guardar su orden;
ver capacidad y transporte actualizados; liberar y reasignar; rechazar planes incompatibles y cambios
simultáneos; conservar asignaciones al recargar mientras FastAPI siga activo. Compilación y pruebas
automáticas aprobadas. Revisión visual aplazada por el usuario.

## Hito 5: requisitos y decisiones de implementación

Requisitos de Monami.md: el conductor consulta pedidos, productos, cantidades, contactos,
direcciones, paradas y recorrido; la empresa comparte el seguimiento y el cliente consulta el avance
sin recibir información de otros pedidos. Los botones de problemas y entrega pertenecen al recorrido
funcional completo y se implementarán en los hitos 6 y 8, respectivamente.

Decisiones propuestas para esta simulación, pendientes de revisión del hito:

- Dos conductores ficticios seleccionables permiten comprobar la consulta de viajes propios.
  La empresa asigna un conductor disponible a un camión con carga guardada.
- Cada conductor y camión tienen un solo viaje activo. El manifiesto conserva una copia del orden,
  productos, cantidades, contactos, referencias y puntos de entrega de todas sus paradas.
- Estados del viaje: `asignado → carga_confirmada → en_camino`. El conductor debe confirmar la
  carga antes de iniciar. Asignar o confirmar carga conserva el pedido en `listo_para_salir`;
  iniciar mueve todos sus pedidos a `en_camino` y registra la salida real en UTC.
- La primera fecha programada del manifiesto se muestra como referencia. Para ensayar la demo,
  se permite iniciar aunque esa fecha sea futura. Las estimaciones de entrega manuales se conservan.
- Desde la asignación se bloquean los cambios de carga, orden y fechas. La empresa puede liberar
  el viaje antes de su salida para ajustar el plan o cambiar de conductor. El estado `cancelado`
  representa esa liberación del viaje; no cancela pedidos ni retira su carga del camión.
- El avance es manual, en pasos de 25%, sin retrocesos ni movimiento por reloj. FastAPI estima la
  posición interpolando el trazado geométrico guardado. No representa GPS ni navegación reales.
- Si faltan coordenadas, el conductor conserva direcciones y contactos y puede simular el porcentaje,
  pero no se estima posición después de salir de la bodega. El mapa mantiene los tramos incompletos.
- Empresa y conductor consultan el mismo manifiesto, estado, porcentaje y posición. El cliente
  recibe solo su código, destino, vehículo, conductor, salida, porcentaje global del vehículo y
  posición simulada; no se publican otras paradas, contactos, direcciones ni códigos.
- El mapa del cliente dibuja una referencia entre bodega y su propio destino y el marcador del
  vehículo; no revela ni pretende representar el itinerario completo.
- Llegar al 100% del recorrido no confirma entregas, ni libera conductor o camión. El viaje permanece
  activo hasta el cierre previsto en el hito 8. Los pedidos siguen en `en_camino` sin fecha de entrega.
- Cada acción comprueba la revisión del viaje, rol y asignación; se conserva historial con autor
  y fecha. Crear un viaje usa la revisión global de planificación. Liberar e iniciar son atómicos:
  dos acciones incompatibles simultáneas no pueden aplicarse ambas.
- Las vistas consultan cambios cada cinco segundos y conservan el estado al recargar el navegador.
  Reiniciar FastAPI borra viajes y pedidos. Se mantiene el stack y no se añaden dependencias.

Criterios de aceptación: preparar y asignar pedidos, crear viaje, revisar manifiesto desde su
conductor, confirmar carga, iniciar y simular avance; comprobar actualización en empresa y cliente,
aislamiento de actores, bloqueos de planificación y conflictos concurrentes. Compilación, análisis
de código, pruebas automáticas y recorrido HTTP; revisión visual pendiente.

## Hito 6: requisitos y decisiones de implementación

Requisitos de Monami.md: informar bloqueos y accidentes, mostrar una alternativa y actualizar
la estimación; el conductor marca pedidos con problema y la empresa puede reprogramarlos,
conservando la información y el historial de intentos. Empresa, conductor y cliente consultan
los cambios que corresponden a su recorrido.

Decisiones propuestas para esta simulación, pendientes de revisión del hito:

- Empresa y conductor asignado pueden reportar bloqueo o accidente durante un viaje en camino,
  antes del 100%. Se exige motivo. Solo hay un incidente de ruta abierto y el avance queda pausado.
- La empresa previsualiza un desvío geométrico desde la posición actual; no se guarda hasta aprobar.
  El mapa compara el recorrido anterior, el actual y la alternativa. No se consultan carreteras,
  tránsito ni rutas reales. Si faltan coordenadas no se propone alternativa.
- La empresa puede aprobar el desvío o continuar el recorrido actual, con nota y demora manual
  de 0 a 1440 minutos. Se conserva posición y porcentaje y el avance posterior usa el recorrido restante.
  Las estimaciones activas pasan a `max(estimación previa o ahora, ahora) + demora`.
  Es una regla de simulación, pendiente de reemplazar por una política de tiempos de producto.
- El cliente ve una alerta general y su estimación; no recibe otros pedidos ni el trazado del viaje.
  Empresa y conductor consultan motivos, decisiones, autores, fechas e historial de incidentes.
- El conductor registra un problema por pedido en camino, incluso al 100% del recorrido. Se crea
  un intento pendiente con motivo y salida real. No admite otro problema pendiente para ese pedido;
  un problema individual no pausa por sí solo el vehículo.
- Solo la empresa reprograma un pedido con problema pendiente. Debe indicar salida futura,
  estimación opcional igual o posterior y nota. Se conserva el código, productos, contacto e intentos.
  Transición excepcional: `en_camino → listo_para_salir`, con nuevas fechas y sin asignaciones.
- Se retira la parada del recorrido activo y se libera su capacidad, conservando el manifiesto
  original como historial. El pedido vuelve a planificación para otro viaje. Avanzar o resolver
  incidentes del viaje anterior no modifica el pedido liberado ni su nueva asignación.
- Si todos los pedidos se reprograman, el viaje se archiva como `reprogramado`, se resuelve el
  incidente abierto si existe y se liberan conductor y camión. No se confirma ninguna entrega.
- Se asume disponibilidad inmediata de la carga reprogramada para ensayar. Retorno físico a bodega,
  devoluciones, entrega parcial y comprobantes están pendientes; no se simula una logística inexistente.
- Mutaciones atómicas con revisión del viaje y, cuando corresponde, del pedido. Ante cambios
  simultáneos se devuelve `409` sin sobrescribir versiones ni duplicar historial.
- Sin dependencias nuevas, Supabase ni cambios de autenticación. Persiste únicamente en memoria.

Criterios de aceptación: reportar un incidente desde empresa o conductor, impedir avance mientras
está abierto, comparar y aprobar alternativa sin salto de posición, actualizar estimaciones y alertas;
registrar intento fallido, reprogramar con el mismo código y planificarlo de nuevo sin que el viaje
anterior lo modifique. Cubrir roles, datos ajenos, revisiones, fechas inválidas y concurrencia.
Compilación, análisis de código y pruebas aprobados: 161 pruebas, 6 de PostgreSQL omitidas.
Guía manual en README.md; revisión visual pendiente. Aliados y entrega se mantienen en hitos 7 y 8.

## Hito 7: requisitos y decisiones de implementación

Requisitos de Monami.md: identificar pedidos que no cubre la flota, asignarlos a una paquetería aliada,
mostrar nombre y contacto y permitir solicitar el servicio, distinguir pendiente de aceptación y
confirmado, y mantener el pedido dentro del seguimiento general como “Entrega por tercero”.
El plan aprobado incluye despacho y seguimiento simulado; el cierre conserva su hito 8.

Decisiones propuestas para esta simulación, pendientes de revisión del hito:

- Apartado de empresa **Entrega por tercero**, con PaqueteríaTest y EnvíosTest. Contactos ficticios
  terminados en `.test`, sin API externa, tarifas, cotización ni alta administrativa de aliados.
- FastAPI identifica pedidos listos, con salida programada y sin transporte. Publica una evaluación
  según carga, capacidad restante, día reservado y viaje bloqueado de cada camión. Puede filtrarse
  por falta de camión compatible. No se infiere cobertura geográfica ni disponibilidad del aliado
  o del conductor; la empresa aporta un motivo obligatorio para elegir un tercero.
- Se puede elegir tercero aunque exista capacidad de flota, para ensayar falta de cobertura u otra
  razón operativa. No se divide la carga entre transportistas ni se asigna automáticamente.
- La empresa elige aliado y registra una solicitud simulada. Se genera referencia de prueba y se
  conserva el mismo código de pedido. “Copiar contacto” y “Copiar solicitud” copian texto al portapapeles;
  no envían mensajes. La aceptación se simula con una acción explícita de empresa, sin nuevo rol.
- Estados del servicio: `pendiente_aceptacion → confirmado → en_camino`. Las dos primeras etapas
  conservan el pedido `listo_para_salir`; el despacho cambia a `en_camino` y registra salida real
  de la simulación. Puede despacharse antes de la fecha programada para facilitar el ensayo.
- Un servicio activo excluye el pedido de flota. Antes de solicitarlo se exige liberar cualquier
  camión o viaje propio. Se bloquean cambios de fechas hasta cancelar el servicio.
- Empresa puede cancelar con motivo antes del despacho: se archiva el servicio y se libera el
  mismo pedido para flota u otro aliado. Motivo, referencia, actores y fechas quedan en historial.
- Empresa simula el avance externo en pasos del 25%. El cliente propietario ve aliado, estado,
  fechas, referencia y porcentaje, sin datos de otros pedidos. No se publica GPS ni ruta ficticia
  del aliado. El 100% no confirma entrega; sigue `en_camino`.
- Los conductores propios no reciben estos pedidos en sus manifiestos. Un pedido reprogramado
  desde flota puede solicitar tercero; el viaje anterior no modifica su nuevo servicio.
- Cada cambio valida la revisión del pedido bajo el bloqueo compartido de planificación. Dos acciones
  incompatibles simultáneas no pueden aplicarse ambas; `409` conserva el estado sin cambios parciales.
- Todo permanece en memoria, sin nuevas dependencias, comunicaciones externas o conexión Supabase.

Criterios de aceptación: identificar falta de capacidad (por ejemplo, un pedido de 61 unidades),
solicitar aliado, distinguir pendiente y confirmado, despachar y ver avance desde cliente con el
mismo código; cancelar antes de despacho y reasignar conservando historial. Rechazar actores ajenos,
datos inválidos, fechas bloqueadas, revisiones obsoletas y doble asignación. Compilación TypeScript/Vite,
Ruff y pruebas aprobados: 196 pruebas, 6 de PostgreSQL omitidas. Recorrido HTTP completo aprobado;
revisión visual pendiente. La guía manual está en README.md. El cierre se incorpora en el hito 8 siguiente.

## Hito 8: requisitos y decisiones de implementación

Requisitos de Monami.md: conductor registra la entrega, empresa consulta el pedido actualizado,
cliente recibe confirmación y fecha de entrega; los problemas mantienen motivo y reprogramación.
El ensayo integra pedido, preparación, planificación, incidente, tercero y cierre. Decisión del usuario:
empresa simula la confirmación de entrega por tercero.

Decisiones propuestas para esta simulación, pendientes de revisión del hito:

- El conductor confirma únicamente pedidos pendientes de su propio viaje en camino. La empresa
  confirma servicios de terceros ya despachados. Se registra fecha UTC en FastAPI, autor e historial;
  puede incluirse nota opcional de hasta 1000 caracteres. Transición `en_camino → entregado`.
- No se exige el 100% ni proximidad GPS, porque ambos recorridos son simulados. La confirmación
  es explícita y el avance por sí solo nunca entrega. El porcentaje no se fuerza al cerrar.
- Un incidente de ruta abierto impide confirmar entregas propias. Un pedido con problema debe
  reprogramarse y entregarse en otro intento; se conserva el mismo código y el historial anterior.
- Cada pedido entregado sale de la carga y del recorrido activos. Las siguientes acciones de avance
  o incidentes afectan solo a pedidos pendientes. No cambian la estimación ni historial del entregado.
- Cuando todos los pedidos originales están entregados o reprogramados, el viaje registra fecha
  de cierre y libera camión y conductor. Estado `completado` si hubo alguna entrega, `reprogramado`
  si se reprogramaron todos. Se conserva manifiesto y resultado por parada en empresa y conductor.
- La liberación permite reutilizar recursos inmediatamente para ensayar; el regreso físico a bodega
  y el tiempo hasta una nueva disponibilidad quedan fuera de esta simulación.
- El pedido entregado conserva referencias de transporte como historial y no admite reapertura,
  reasignación, cambios de fechas o doble entrega. Su seguimiento final muestra fecha de entrega
  sin ubicación del vehículo ni incidentes posteriores de otros pedidos.
- La empresa separa servicios externos abiertos y entregados. El cliente mantiene el tracker general,
  aliado y referencia, con confirmación final explícitamente simulada por empresa.
- Cada entrega propia comprueba revisiones del viaje y pedido; tercero comprueba la del pedido.
  Las operaciones son atómicas frente a avances, problemas, reprogramaciones y envíos duplicados.
- Sin dependencias nuevas ni comunicaciones externas. Datos en memoria local y stack acordado.
  Firma, foto, comprobantes, entregas parciales y notificaciones no se incluyen.

Criterios de aceptación: entregar pedidos propios y de terceros, comprobar fechas y última etapa
del cliente, conservar historial de intentos, completar un viaje mixto con reprogramaciones y
reutilizar sus recursos. Rechazar confirmaciones antes de salida, actores ajenos, revisiones
obsoletas, campos falsificados y cambios de pedidos entregados. TypeScript/Vite y Ruff aprobados;
230 pruebas aprobadas y 6 de PostgreSQL omitidas. Ensayo HTTP de extremo a extremo aprobado;
revisión visual pendiente. Guía manual en README.md. Supabase y despliegue conservan su hito 9.

## Hito 9: alcance de demo desplegada

Decisiones del usuario: escenario preparado y reiniciable; React + Vite + TypeScript consume solo
FastAPI, que accede a PostgreSQL gestionado por Supabase. El usuario configurará la URL real al terminar
la preparación del hito. Repositorio: `Joseswings/MONAMI`. Se evaluaron Cloudflare y Vercel; proveedor final pendiente.

Solución propuesta para acotar la demo:

- Persistir el agregado completo del escenario en JSONB, con versión de formato, y conservar las reglas
  de los hitos anteriores. Es una tabla de escenarios y otra de sesiones de pitch, añadidas por Alembic.
  No se implementa todavía el modelo normalizado para operación real, analítica o múltiples empresas.
- Cada lectura operativa o mutación usa una transacción y bloqueo de fila PostgreSQL. La actualización
  completa del agregado se confirma solo si la acción es válida, evitando sobrescrituras entre instancias.
- Escenario compartido de seis pedidos ficticios: recibido, en preparación, listo sin cobertura de
  capacidad, dos en un viaje al 25% y uno entregado por aliado. Actores, contactos y flota son de prueba.
- Carga explícita e idempotente mediante `app.pitch_seed`. No crea tablas ni carga datos al arrancar.
  Reiniciar FastAPI conserva el estado; restaurar el pitch es una acción distinta del presentador.
- Acceso mediante clave compartida del backend y sesiones con tokens opacos guardados como hash y
  con vencimiento. El token permanece solo en memoria del navegador. Elegir roles sigue siendo un ensayo,
  no identidad ni permisos de empleados reales. La infraestructura Argon2 del hito 1 queda disponible aparte.
- Reinicio con segunda clave distinta, confirmación y comprobación de versión. Reemplaza únicamente
  el escenario configurado, conserva otras tablas y escenarios y genera nuevos códigos. Las pestañas
  antiguas no pueden aplicar mutaciones hasta actualizar, aunque coincida una revisión numérica.
- Límite de 100 pedidos y 2 MB por escenario para mantener el volumen de una presentación.
- CORS con orígenes explícitos, credenciales PostgreSQL solo en backend y conexión cifrada. RLS sin
  políticas públicas en tablas de pitch; ninguna clave o dependencia Supabase en React.
- Preparación de frontend para Cloudflare Pages y Vercel, backend para Docker y Vercel Python.
  No se contrata ni crea un servicio remoto hasta disponer de proveedor, variables y URLs finales.

Verificado: TypeScript/Vite, Ruff, escenario preparado y serialización, idempotencia, historial,
transiciones después de restaurar el agregado, acceso y errores controlados, rechazo de versiones
anteriores y propagación de la versión entre FastAPI y el almacén. El lock de dependencias es válido.
Resultado: 249 pruebas aprobadas y 10 de PostgreSQL omitidas. HTTP comprueba acceso, fallo controlado
sin base, contratos y CORS; no sustituye la integración real.
Se añadieron pruebas de PostgreSQL para persistencia entre instancias, reinicio aislado, sesiones y
concurrencia; requieren base separada y aún están omitidas. Docker está instalado pero su daemon
no estaba activo, por lo que la imagen no se ha construido. La revisión visual sigue pendiente.

Aceptación final pendiente: configurar `DATABASE_URL`, dos claves y la base de pruebas; aplicar
migración y carga explícitas, verificar persistencia real y conflictos en PostgreSQL, publicar ambos
servicios y repetir el recorrido desde las URLs HTTPS. Guía completa en [DEPLOYMENT.md](DEPLOYMENT.md).

## Pendientes de producto

- Datos reales de empresa, catálogo, unidades y capacidad de camiones.
- Modelo real de carga (peso/volumen/bultos), bodega real, múltiples viajes por camión,
  horarios de salida compartidos y ventanas de entrega.
- Registro de clientes y alta de empleados/conductores; vinculación a organizaciones.
- Proveedor y alcance de mapas/rutas reales, criterios de cercanía y necesidad de PostGIS.
- Reglas para cancelaciones, rechazo, devolución, entregas parciales y comprobantes.
- Política real de demoras y estimaciones, aprobación de desvíos y retorno de carga reprogramada a bodega.
- Aliados reales, cobertura y tarifas, canal de solicitud/aceptación, referencias y seguimiento externo;
  cancelaciones, incidencias y reprogramaciones después del despacho por tercero.
- Infraestructura de alojamiento, autenticación para acceso público y configuración real de Supabase.
