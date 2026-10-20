import { useState } from 'react'
import { demoApi } from '../api'
import type { DemoActor, DriverAction, Trip } from '../api'
import RouteMap from './RouteMap'
import { formatDate } from './OrderParts'
import { useLiveData } from './useLiveData'
import { useDemoAction } from './useDemoAction'
import { DeliveryProblemForm, IncidentControls, RescheduleForm } from './TripIncidents'
import DeliveryConfirmation from './DeliveryConfirmation'

const statusLabels = { asignado: 'Pendiente de confirmar carga', carga_confirmada: 'Carga confirmada', en_camino: 'En camino', cancelado: 'Viaje liberado', reprogramado: 'Viaje cerrado por reprogramación', completado: 'Viaje completado' }

export function CompanyTrips({ actor }: { actor: DemoActor }) {
  const { data, error, refresh, publish } = useLiveData(actor.id, () => demoApi.trips(actor.id))
  const action = useDemoAction()
  const [truckId, setTruckId] = useState('')
  const [driverId, setDriverId] = useState('')
  const availableDrivers = data?.drivers.filter(driver => driver.available) || []
  return <section className="panel" aria-busy={action.busy}>
    <p className="eyebrow">Empresa · Salida y seguimiento</p><h1>Viajes de la flota</h1>
    <p className="intro">Asigna un conductor a la carga guardada del camión. El conductor revisará sus productos antes de salir.</p>
    <button className="secondary compact" onClick={refresh}>Actualizar viajes</button>
    {error && <p className="error" role="alert">{error} Los datos pueden estar desactualizados.</p>}
    {action.error && <p className="error" role="alert">{action.error} Actualiza antes de volver a intentarlo.</p>}
    {action.message && <p className="info" role="status">{action.message}</p>}
    {!data && !error && <p role="status">Consultando viajes…</p>}
    {data && <>
      {data.trips.some(trip => trip.active_incident_id || trip.stops.some(stop => stop.delivery_status === 'con_problema')) && <div className="incident-alert" role="alert"><strong>Hay incidentes o pedidos con problema por atender.</strong><p>Revisa las alertas y los formularios de cada viaje.</p></div>}
      <form className="dispatch-form" onSubmit={event => {
        event.preventDefault()
        void action.perform(async () => {
          await demoApi.createTrip(actor.id, data.revision, truckId, driverId)
          const value = await demoApi.trips(actor.id)
          if (action.isMounted()) { publish(value); setTruckId(''); setDriverId('') }
        }, 'Viaje asignado. El conductor ya puede consultar la carga y confirmar su salida.')
      }}><h2>Asignar viaje</h2><fieldset disabled={action.busy || Boolean(error)}><div className="field-grid">
        <div><label htmlFor="trip-truck">Camión con carga guardada</label><select id="trip-truck" required value={truckId} onChange={event => setTruckId(event.target.value)}>
          <option value="">Seleccionar camión</option>{data.dispatchable_trucks.map(truck => <option value={truck.id} key={truck.id}>{truck.name} · {truck.order_codes.length} pedidos · {truck.used_capacity} unidades</option>)}
        </select></div>
        <div><label htmlFor="trip-driver">Conductor disponible</label><select id="trip-driver" required value={driverId} onChange={event => setDriverId(event.target.value)}>
          <option value="">Seleccionar conductor</option>{availableDrivers.map(driver => <option value={driver.id} key={driver.id}>{driver.name}</option>)}
        </select></div>
      </div><button type="submit" className="compact" disabled={!data.dispatchable_trucks.length || !availableDrivers.length}>Asignar viaje al conductor</button></fieldset>
        {!data.dispatchable_trucks.length && <p className="hint">Guarda pedidos en un camión desde <a href="#planificacion">Planificar entregas</a> para crear un viaje.</p>}
        {!availableDrivers.length && <p className="hint">Todos los conductores tienen un viaje asignado.</p>}
        <p className="hint">La asignación bloquea cambios de carga y fechas. Antes de salir puedes liberar el viaje para ajustar el plan; los pedidos siguen en el camión.</p>
      </form>
      <h2>Viajes activos ({data.trips.filter(trip => !['cancelado', 'reprogramado', 'completado'].includes(trip.status)).length})</h2>
      {data.trips.length === 0 && <div className="empty-state"><p>Todavía no hay viajes asignados.</p></div>}
      {data.trips.map(trip => <details className="trip-card" key={trip.id} open={!['cancelado', 'reprogramado', 'completado'].includes(trip.status)}>
        <summary>{trip.truck_name} · {trip.driver_name} · {statusLabels[trip.status]}</summary>
        <TripView trip={trip} actor={actor} onChanged={refresh} disabled={Boolean(error) || action.busy} />
        {(trip.status === 'asignado' || trip.status === 'carga_confirmada') && <button className="secondary compact" disabled={action.busy || Boolean(error)} onClick={() => {
          void action.perform(async () => {
            await demoApi.cancelTrip(actor.id, trip)
            const value = await demoApi.trips(actor.id)
            if (action.isMounted()) publish(value)
          }, 'Viaje liberado. El conductor está disponible y puedes ajustar la carga guardada del camión.')
        }}>Liberar viaje antes de salir</button>}
      </details>)}
    </>}
  </section>
}

export function DriverWorkspace({ actor }: { actor: DemoActor }) {
  const { data: trip, error, refresh, publish } = useLiveData(actor.id, () => demoApi.driverTrip(actor.id))
  const closed = useLiveData(`${actor.id}:closed`, () => demoApi.driverClosedTrips(actor.id))
  const action = useDemoAction()
  function act(command: DriverAction, message: string) {
    if (!trip) return
    void action.perform(async () => {
      const value = await demoApi.driverAct(actor.id, trip, command)
      if (action.isMounted()) publish(value)
    }, message)
  }
  return <section className="panel driver-workspace" aria-busy={action.busy}>
    <p className="eyebrow">Mi viaje</p><h1>{actor.name}</h1>
    <button className="secondary compact" onClick={refresh}>Actualizar mi viaje</button>
    {error && <p className="error" role="alert">{error} La información puede estar desactualizada.</p>}
    {action.error && <p className="error" role="alert">{action.error} Actualiza antes de volver a intentarlo.</p>}
    {action.message && <p className="info" role="status">{action.message}</p>}
    {trip === undefined && !error && <p role="status">Consultando tu viaje…</p>}
    {trip === null && <div className="empty-state"><h2>No tienes un viaje asignado</h2><p>La empresa debe asignarte un camión con su carga guardada. Este espacio se actualizará automáticamente.</p></div>}
    {trip && <>
      <div className="driver-actions"><fieldset disabled={action.busy || Boolean(error)}>
        {trip.status === 'asignado' && <><p>Revisa los productos, cantidades y contactos de cada parada antes de confirmar.</p><button onClick={() => act('confirm_load', 'Carga confirmada. Ya puedes iniciar el viaje.')}>Confirmar carga revisada</button></>}
        {trip.status === 'carga_confirmada' && <><p className="info">Simulación local: puedes iniciar antes de la fecha programada para ensayar el recorrido.</p><button onClick={() => act('start_trip', 'Viaje iniciado. Empresa y clientes verán sus pedidos En camino.')}>Iniciar viaje</button></>}
        {trip.status === 'en_camino' && <button disabled={trip.progress_percent === 100 || Boolean(trip.active_incident_id)} onClick={() => act('advance', 'Avance simulado actualizado para empresa y clientes.')}>Simular avance +25%</button>}
      </fieldset></div>
      <TripView trip={trip} actor={actor} onChanged={value => {
        if (value) { publish(['completado', 'reprogramado'].includes(value.status) ? null : value); closed.refresh() }
        else refresh()
      }} disabled={Boolean(error) || action.busy} />
    </>}
    <h2>Mis viajes cerrados</h2>
    {closed.error && <p className="error" role="alert">{closed.error} <button className="text-button" onClick={closed.refresh}>Actualizar historial</button></p>}
    {closed.data?.length === 0 && <p className="hint">Todavía no tienes viajes cerrados.</p>}
    {closed.data?.map(item => <details className="trip-card" key={item.id}><summary>{item.truck_name} · {statusLabels[item.status]} · {formatDate(item.closed_at)}</summary>
      <TripView trip={item} actor={actor} onChanged={closed.refresh} disabled />
    </details>)}
    <p className="hint">Actualización cada 5 segundos. Las posiciones y el avance son simulados. Cada entrega requiere confirmación explícita.</p>
  </section>
}

function TripView({ trip, actor, onChanged, disabled }: { trip: Trip; actor: DemoActor; onChanged: (trip?: Trip) => void; disabled: boolean }) {
  const activeStops = trip.stops.filter(stop => !trip.excluded_order_codes.includes(stop.code) && !trip.completed_order_codes.includes(stop.code))
  const incident = trip.incidents.find(item => item.id === trip.active_incident_id)
  const previous = [...trip.incidents].reverse().find(item => item.decision === 'alternativa')
  return <div className="trip-view">
    <p className="status-tag">{statusLabels[trip.status]}</p>
    <dl className="delivery-facts"><div><dt>Camión y conductor</dt><dd>{trip.truck_name}<br />{trip.driver_name}</dd></div>
      <div><dt>Carga inicial simulada</dt><dd>{trip.load_units} / {trip.capacity} unidades · {activeStops.length} pedidos vigentes de {trip.stops.length} iniciales</dd></div>
      <div><dt>Primera salida programada</dt><dd>{formatDate(trip.planned_departure_at)}</dd></div>
      <div><dt>Salida registrada</dt><dd>{formatDate(trip.actual_departure_at, 'Aún no inicia')}</dd></div></dl>
    <p>{trip.completed_order_codes.length} entregados · {trip.excluded_order_codes.length} reprogramados · {activeStops.length} pendientes.</p>
    {trip.closed_at && <p className="delivery-receipt">Viaje cerrado el {formatDate(trip.closed_at)}. Camión y conductor liberados para otra planificación.</p>}
    {trip.status === 'en_camino' && <div className="trip-progress"><label>Avance del recorrido simulado: {trip.progress_percent}%<progress max={100} value={trip.progress_percent} /></label>
      {trip.progress_percent === 100 && <p className="info">Recorrido simulado completado. Los pedidos siguen pendientes de confirmación de entrega.</p>}
      {!trip.position && <p className="hint">No se estima posición porque faltan coordenadas en el recorrido. Revisa las direcciones de la lista.</p>}
    </div>}
    <IncidentControls actor={actor} trip={trip} onChanged={onChanged} disabled={disabled} />
    <h2>Recorrido y paradas</h2><RouteMap depot={trip.depot} stops={trip.closed_at ? trip.stops : activeStops} vehiclePosition={trip.position} routePoints={trip.route_points} incidentPosition={incident?.position} referencePoints={!incident ? previous?.route_before : undefined} />
    <h2>Manifiesto y resultado de cada pedido</h2><ol className="trip-manifest">{trip.stops.map(stop => <li key={stop.code}>
      <h3>Parada {stop.position} · {stop.code}</h3><p className="preserve-lines">{stop.address}</p>
      <p>{stop.contact_name}<br /><span className="contact-value">{stop.contact_phone}</span><br /><span className="contact-value">{stop.contact_email}</span></p>
      {stop.instructions && <p className="info preserve-lines">{stop.instructions}</p>}
      <ul className="product-list">{stop.items.map((item, index) => <li key={index}><span>{item.product}</span><strong>{item.quantity} unidades</strong></li>)}</ul>
      <p>Entrega estimada: {formatDate(stop.estimated_delivery_at, 'Por estimar')}</p>
      {stop.delivery_status === 'con_problema' && <p className="incident-alert preserve-lines" role="alert"><strong>Entrega con problema:</strong> {stop.problem_reason}</p>}
      {stop.delivery_status === 'reprogramado' && <p className="info preserve-lines">Pedido reprogramado y retirado de este viaje.<br />Motivo del intento: {stop.problem_reason}<br />Nueva salida: {formatDate(stop.rescheduled_departure_at)}</p>}
      {stop.delivery_status === 'entregado' && <p className="delivery-receipt">Entregado el {formatDate(stop.delivered_at)}.</p>}
      {trip.status === 'en_camino' && stop.delivery_status === 'pendiente' && actor.role === 'conductor' && <DeliveryConfirmation actor={actor} trip={trip} stop={stop} onChanged={onChanged} disabled={disabled} />}
      {trip.status === 'en_camino' && stop.delivery_status === 'pendiente' && actor.role === 'conductor' && <DeliveryProblemForm actor={actor} trip={trip} stop={stop} onChanged={onChanged} disabled={disabled} />}
      {trip.status === 'en_camino' && stop.delivery_status === 'con_problema' && actor.role === 'empresa' && <RescheduleForm actor={actor} trip={trip} stop={stop} onChanged={onChanged} disabled={disabled} />}
      {!stop.location && <p className="hint">Sin punto en el mapa; usa la dirección y las referencias.</p>}
    </li>)}</ol>
    <details className="order-history"><summary>Historial del viaje</summary><ol>{trip.history.map((event, index) => <li key={index}>
      <strong>{event.action}</strong><span className="hint">{formatDate(event.at)} · {event.actor_name}</span>
    </li>)}</ol></details>
  </div>
}

export function CustomerTrackingPanel({ actor, code }: { actor: DemoActor; code: string }) {
  const { data, error, refresh } = useLiveData(`${actor.id}:${code}`, () => demoApi.tracking(actor.id, code))
  return <section className="customer-tracking"><h2>Seguimiento de tu vehículo</h2>
    {error && <p className="error" role="alert">{error} El seguimiento puede estar desactualizado. <button className="text-button" onClick={refresh}>Actualizar</button></p>}
    {!data && !error && <p role="status">Consultando seguimiento…</p>}
    {data && <>
      {data.delivery_mode === 'tercero' ? <p>Entrega por tercero · {data.partner_name} · {data.service_reference}</p> : <p>{data.truck_name || 'Camión por asignar'}{data.driver_name ? ` · ${data.driver_name}` : ''}</p>}
      {data.status === 'entregado' ? <p className="delivery-receipt">Tu pedido fue entregado el {formatDate(data.delivered_at)}. Su seguimiento está cerrado.</p> : <p className="info">{data.delivery_mode === 'tercero' ? data.status === 'en_camino' ? `En camino por tercero. Avance manual simulado: ${data.progress_percent}%. Sin ubicación GPS del aliado.` : data.status === 'confirmado' ? 'El aliado tiene aceptación simulada; pendiente de despacho.' : 'Servicio por tercero pendiente de aceptación simulada.' : data.status === 'en_camino' ? `Tu pedido está En camino. Avance del recorrido simulado del vehículo: ${data.progress_percent}%.` : data.status === 'carga_confirmada' ? 'El conductor confirmó la carga y está pendiente de iniciar el viaje.' : data.status === 'asignado' ? 'La empresa asignó el viaje. El conductor revisará la carga antes de salir.' : 'Tu pedido todavía no tiene un viaje asignado.'}</p>}
      {data.incident_message && <p className="incident-alert" role="alert">{data.incident_message}</p>}
      {data.needs_reschedule && <p className="incident-alert">Hay un inconveniente con tu entrega. La empresa está revisando la reprogramación.</p>}
      <p>Entrega estimada actual: {formatDate(data.estimated_delivery_at, 'Por estimar')}</p>
      {data.status === 'en_camino' && data.delivery_mode !== 'tercero' && <>
        <progress max={100} value={data.progress_percent} aria-label="Avance simulado del vehículo" />
        <p>Salida registrada: {formatDate(data.actual_departure_at)}</p>
        <RouteMap depot={data.depot} stops={[{ position: 1, code: data.code, address: 'Tu destino de entrega', location: data.destination, load_units: 0 }]} vehiclePosition={data.position} />
        <p className="hint">El mapa muestra la bodega y tu destino como referencia, junto al avance simulado del vehículo. La línea de referencia no representa el itinerario completo.</p>
        {!data.position && <p className="hint">El recorrido no tiene todas sus coordenadas; no se estima la posición del vehículo.</p>}
        {data.progress_percent === 100 && <p className="info">El recorrido simulado llegó al 100%. La confirmación de entrega de tu pedido sigue pendiente.</p>}
      </>}
    </>}
  </section>
}
