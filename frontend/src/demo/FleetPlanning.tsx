import { useEffect, useRef, useState } from 'react'
import { demoApi } from '../api'
import type { DemoActor, FleetSnapshot, FleetSuggestion, Order, PlannedStop, Truck } from '../api'
import RouteMap from './RouteMap'
import { formatDate } from './OrderParts'

function departureDay(order: Order) {
  return order.scheduled_departure_at ? new Date(new Date(order.scheduled_departure_at).getTime() - 6 * 3600000).toISOString().slice(0, 10) : ''
}
function units(order: Order) { return order.items.reduce((total, item) => total + item.quantity, 0) }
function dayLabel(day: string | null) {
  return day ? new Intl.DateTimeFormat('es-GT', { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(`${day}T12:00:00Z`)) : 'Sin reserva'
}

const availability = { disponible: 'Disponible', reservado: 'Reservado con espacio', completo: 'Capacidad completa', viaje_asignado: 'Viaje asignado', en_viaje: 'En viaje' }

export default function FleetPlanning({ actor }: { actor: DemoActor }) {
  const [snapshot, setSnapshot] = useState<FleetSnapshot | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [truckId, setTruckId] = useState('camion-1')
  const sequence = useRef(0)
  useEffect(() => {
    let active = true
    const load = async () => {
      const ticket = ++sequence.current
      try {
        const data = await demoApi.planning(actor.id)
        if (active && ticket === sequence.current) { setSnapshot(data); setError('') }
      } catch (failure) {
        if (active && ticket === sequence.current) setError(failure instanceof Error ? failure.message : 'No pudimos consultar la flota.')
      }
    }
    void load()
    const timer = window.setInterval(load, 5000)
    return () => { active = false; ++sequence.current; window.clearInterval(timer) }
  }, [actor.id, attempt])
  const truck = snapshot?.trucks.find(item => item.id === truckId)
  return <section className="panel">
    <p className="eyebrow">Planificación de empresa</p><h1>Prepara el reparto</h1>
    <p className="intro">Elige un camión y un día de salida, revisa la agrupación y confirma sus pedidos.</p>
    <p className="info">Flota y capacidad de prueba. Una unidad solicitada ocupa una unidad de carga simulada. Cada camión conserva un plan hasta que retires sus pedidos.</p>
    <p><a href="#terceros">¿La flota no cubre un pedido? Revisar entrega por tercero →</a></p>
    <div className="actions"><button className="secondary compact" onClick={() => setAttempt(value => value + 1)}>Actualizar planificación</button>
      <span className="hint">Actualización automática cada 5 segundos.</span></div>
    {error && <p className="error" role="alert">{error} {snapshot && 'Los datos mostrados pueden estar desactualizados.'}</p>}
    {!snapshot && !error && <p role="status">Consultando camiones y pedidos…</p>}
    {snapshot && <>
      <div className="truck-grid" role="group" aria-label="Seleccionar camión">{snapshot.trucks.map(item => <button className="truck-card" key={item.id} aria-pressed={item.id === truckId} onClick={() => setTruckId(item.id)}>
        <strong>{item.name}</strong><span>{availability[item.availability]}</span>
        <span>{item.used_capacity} / {item.capacity} unidades · {item.remaining_capacity} libres</span>
        <meter min={0} max={item.capacity} value={item.used_capacity} aria-label={`Ocupación de ${item.name}`} />
        <span>{dayLabel(item.departure_date)} · {item.order_codes.length} pedidos</span>
      </button>)}</div>
      {snapshot.ready_orders.length === 0 && <p className="info">Todavía no hay pedidos listos para salir. Prepara un pedido desde el panel para poder asignarlo.</p>}
      {truck?.trip_id ? <section className="truck-editor"><h2>{truck.name} · {availability[truck.availability]}</h2>
        <p className="info">Su carga está bloqueada por el viaje. <a href="#viajes">Consultar viaje y avance →</a></p>
        <p>{truck.used_capacity} unidades · {truck.stops.length} pedidos.</p><ol>{truck.stops.map(stop => <li key={stop.code}>{stop.code} · {stop.address}</li>)}</ol>
        <RouteMap depot={snapshot.depot} stops={truck.stops} />
      </section> : truck && <TruckEditor key={truck.id} actor={actor} snapshot={snapshot} truck={truck} unavailable={Boolean(error)} onSaved={value => {
        ++sequence.current; setSnapshot(current => current && current.revision > value.revision ? current : value); setError('')
      }} />}
    </>}
  </section>
}

function TruckEditor({ actor, snapshot, truck, unavailable, onSaved }: {
  actor: DemoActor; snapshot: FleetSnapshot; truck: Truck; unavailable: boolean; onSaved: (value: FleetSnapshot) => void
}) {
  const dates = [...new Set(snapshot.ready_orders.map(departureDay).filter(Boolean))].sort()
  const [date, setDate] = useState(truck.departure_date || dates[0] || '')
  const [draft, setDraft] = useState<string[]>(truck.order_codes)
  const [baseRevision, setBaseRevision] = useState(snapshot.revision)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [suggestion, setSuggestion] = useState<FleetSuggestion | null>(null)
  const inFlight = useRef(false)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])
  useEffect(() => {
    if (!dirty) {
      setDraft(truck.order_codes); setBaseRevision(snapshot.revision)
      setDate(previous => truck.departure_date || (dates.includes(previous) ? previous : dates[0] || ''))
    }
  }, [truck, snapshot.revision, dirty])

  const byCode = new Map(snapshot.ready_orders.map(order => [order.code, order]))
  const selected = draft.map(code => byCode.get(code)).filter((order): order is Order => Boolean(order))
  const used = selected.reduce((total, order) => total + units(order), 0)
  const stale = dirty && (snapshot.revision !== baseRevision || draft.some(code => !byCode.has(code)))
  const blocked = busy || unavailable || stale
  const forDate = snapshot.ready_orders.filter(order => departureDay(order) === date)
  const stops: PlannedStop[] = draft.flatMap((code, index) => {
    const order = byCode.get(code)
    return order ? [{ position: index + 1, code, address: order.address, location: order.location, load_units: units(order) }] : []
  })

  function edit(codes: string[]) {
    setDraft(codes); setDirty(true); setMessage(''); setError('')
  }
  function reset() {
    setDraft(truck.order_codes); setBaseRevision(snapshot.revision); setDirty(false)
    setDate(truck.departure_date || dates[0] || ''); setSuggestion(null); setError(''); setMessage('')
  }
  async function perform(operation: () => Promise<void>) {
    if (inFlight.current) return
    inFlight.current = true; setBusy(true); setError(''); setMessage('')
    try { await operation() }
    catch (failure) { if (mounted.current) setError(failure instanceof Error ? failure.message : 'No pudimos completar la planificación.') }
    finally { inFlight.current = false; if (mounted.current) setBusy(false) }
  }
  function suggest() {
    void perform(async () => {
      const result = await demoApi.suggest(actor.id, truck.id, baseRevision, date)
      if (mounted.current) {
        setDraft(result.order_codes); setBaseRevision(result.revision); setSuggestion(result); setDirty(true)
        setMessage('Sugerencia cargada en el borrador. Puedes ajustarla antes de guardar.')
      }
    })
  }
  function save() {
    void perform(async () => {
      const result = await demoApi.assign(actor.id, truck.id, baseRevision, draft.length ? date : null, draft)
      if (mounted.current) {
        onSaved(result); setDirty(false); setSuggestion(null)
        setMessage(draft.length ? 'Asignación guardada. Los pedidos conservan el estado Listo para salir.' : 'Carga liberada. El camión vuelve a estar disponible.')
      }
    })
  }
  function move(index: number, offset: number) {
    const codes = [...draft]
    ;[codes[index], codes[index + offset]] = [codes[index + offset], codes[index]]
    edit(codes)
  }

  return <section className="truck-editor" aria-busy={busy}>
    <h2>{truck.name}</h2>
    <p className="hint">{snapshot.depot_name} · {truck.capacity} unidades de capacidad simulada.</p>
    {stale && <p className="error" role="alert">La planificación cambió mientras editabas. Conservamos tu borrador; carga el plan actual antes de guardar.</p>}
    {error && <p className="error" role="alert">{error} Actualiza la planificación y carga el plan actual si hubo cambios.</p>}
    {message && <p className="info" role="status">{message}</p>}
    <div className="actions"><span className="status-tag">{dirty ? 'Borrador sin guardar' : 'Plan guardado'}</span>
      <button className="text-button" disabled={busy} onClick={reset}>Descartar borrador y cargar plan actual</button></div>
    <fieldset disabled={blocked}>
      <label htmlFor="planning-day">Día de salida · Guatemala</label>
      <select id="planning-day" value={date} disabled={truck.order_codes.length > 0} onChange={event => { setDate(event.target.value); setSuggestion(null); edit([]) }}>
        {!dates.length && <option value="">Sin pedidos listos</option>}
        {dates.map(day => <option key={day} value={day}>{dayLabel(day)}</option>)}
      </select>
      {truck.order_codes.length > 0 && <p className="hint">El camión está reservado para {dayLabel(truck.departure_date)}. Para cambiar de día, vacía la selección y guarda primero.</p>}
      <div className="actions"><button type="button" className="secondary compact" disabled={!date} onClick={suggest}>Proponer agrupación por cercanía</button></div>
      <p className="hint">La sugerencia conserva las paradas guardadas y añade pedidos cercanos que caben en el mismo día. Reemplaza el borrador y necesita tu confirmación.</p>
      {suggestion && suggestion.excluded.length > 0 && <details><summary>Pedidos que la sugerencia dejó fuera ({suggestion.excluded.length})</summary><ul>
        {suggestion.excluded.map(item => <li key={item.code}>{item.code}: {item.reason}</li>)}
      </ul></details>}
      <h3>Pedidos listos del día ({forDate.length})</h3>
      {forDate.length === 0 && <p className="hint">No hay pedidos listos para este día.</p>}
      <ul className="planning-orders">{forDate.map(order => {
        const checked = draft.includes(order.code)
        const elsewhere = Boolean(order.assigned_truck_id && order.assigned_truck_id !== truck.id)
        const tooLarge = !checked && units(order) > truck.capacity - used
        return <li key={order.code}><label className="planning-choice">
          <input type="checkbox" checked={checked} disabled={elsewhere || tooLarge || (!checked && draft.length >= 100)} onChange={() => edit(checked ? draft.filter(code => code !== order.code) : [...draft, order.code])} />
          <span><strong>{order.code} · {order.contact_name}</strong><span>{order.address}</span><span>{units(order)} unidades · Salida: {formatDate(order.scheduled_departure_at)}</span>
            <span className="hint">{elsewhere ? `Asignado a ${order.assigned_truck_name}. Retíralo de ese camión para moverlo.` : tooLarge ? 'No cabe en la capacidad restante.' : !order.location ? 'Sin coordenadas; asignación manual disponible, trazado incompleto.' : 'Punto disponible en el mapa.'}</span>
          </span></label></li>
      })}</ul>
      <h3>Orden de paradas {dirty ? 'del borrador' : 'guardado'}</h3>
      <p className="info">Carga: <strong>{used} / {truck.capacity}</strong> unidades · Libres: <strong>{truck.capacity - used}</strong> · Pedidos: {draft.length}</p>
      {draft.length === 0 ? <p className="hint">Selecciona pedidos o solicita una sugerencia.</p> : <ol className="planned-stops">{draft.map((code, index) => <li key={code}>
        <div><strong>{code}</strong><p>{byCode.get(code)?.address || 'Pedido no disponible; actualiza el plan.'}</p></div>
        <div className="stop-actions"><button type="button" className="secondary compact" aria-label={`Subir parada ${index + 1}`} disabled={index === 0} onClick={() => move(index, -1)}>↑</button>
          <button type="button" className="secondary compact" aria-label={`Bajar parada ${index + 1}`} disabled={index === draft.length - 1} onClick={() => move(index, 1)}>↓</button>
          <button type="button" className="text-button" onClick={() => edit(draft.filter(item => item !== code))}>Quitar</button></div>
      </li>)}</ol>}
      <div className="actions"><button type="button" className="secondary compact" disabled={!draft.length} onClick={() => edit([])}>Vaciar selección</button>
        <button type="button" className="compact" disabled={!dirty || used > truck.capacity || (draft.length > 0 && !date)} onClick={save}>{busy ? 'Guardando…' : 'Guardar asignación'}</button></div>
    </fieldset>
    <h3>{dirty ? 'Vista previa del recorrido simulado' : 'Recorrido simulado guardado'}</h3>
    <RouteMap depot={snapshot.depot} stops={stops} />
    {!dirty && truck.order_codes.length > 0 && truck.straight_line_km !== null && <p className="hint">Suma de distancias en línea recta: {truck.straight_line_km} km. Sin regreso a bodega; no es distancia por carretera.</p>}
    <p className="hint">Asignar reserva capacidad y marca flota propia para el cliente. Tras guardar, <a href="#viajes">asigna un conductor desde Viajes</a>. Cambiar de camión o salir de esta pantalla descarta el borrador sin guardar.</p>
  </section>
}
