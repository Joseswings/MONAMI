import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { demoApi } from '../api'
import type { CompanyAction, DemoActor, Order, OrderStatus } from '../api'
import LocationMap from './LocationMap'
import FleetPlanning from './FleetPlanning'
import { CompanyTrips } from './TripsWorkspace'
import { OrderIssues } from './TripIncidents'
import ThirdPartyWorkspace, { ThirdPartyDetails } from './ThirdPartyWorkspace'
import { OrderSummary } from './OrderForm'
import { DeliveryReceipt, formatDate, OrderHistory, statusLabel, useDemoOrder, useOrderRoute } from './OrderParts'

const groups: { id: string; label: string; statuses: OrderStatus[] }[] = [
  { id: 'received', label: 'Por confirmar', statuses: ['recibido'] },
  { id: 'preparing', label: 'En preparación', statuses: ['confirmado', 'preparando'] },
  { id: 'ready', label: 'Listos para salir', statuses: ['listo_para_salir'] },
  { id: 'transit', label: 'En camino', statuses: ['en_camino'] },
  { id: 'delivered', label: 'Entregados', statuses: ['entregado'] },
]

export default function CompanyWorkspace({ actor }: { actor: DemoActor }) {
  const route = useOrderRoute()
  return <>
    <nav className="workspace-nav" aria-label="Pedidos de empresa"><div><strong>EmpresaTest</strong><span className="hint">Revisión y preparación de pedidos</span></div>
      <div className="nav-links"><a className={!route.planning && !route.trips && !route.thirdParty ? 'selected' : ''} href="#pedidos">Pedidos</a><a className={route.planning ? 'selected' : ''} href="#planificacion">Planificar entregas</a><a className={route.trips ? 'selected' : ''} href="#viajes">Viajes</a><a className={route.thirdParty ? 'selected' : ''} href="#terceros">Entrega por tercero</a></div>
    </nav>
    {route.thirdParty ? <ThirdPartyWorkspace actor={actor} /> : route.trips ? <CompanyTrips actor={actor} /> : route.planning ? <FleetPlanning actor={actor} /> : route.code ? <CompanyDetail key={route.code} actor={actor} code={route.code} /> : <CompanyOrders actor={actor} />}
  </>
}

function CompanyOrders({ actor }: { actor: DemoActor }) {
  const [orders, setOrders] = useState<Order[] | null>(null)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    let sequence = 0
    const load = async () => {
      const ticket = ++sequence
      try {
        const value = await demoApi.companyList(actor.id)
        if (active && ticket === sequence) { setOrders(value); setError('') }
      } catch (failure) {
        if (active && ticket === sequence) setError(failure instanceof Error ? failure.message : 'No pudimos consultar los pedidos.')
      }
    }
    void load()
    const timer = window.setInterval(load, 5000)
    return () => { active = false; window.clearInterval(timer) }
  }, [actor.id, attempt])
  const query = search.trim().toLocaleLowerCase()
  const matching = orders?.filter(order => `${order.code} ${order.contact_name}`.toLocaleLowerCase().includes(query)) || []
  return <section className="panel">
    <p className="eyebrow">Operación de empresa</p><h1>Panel de pedidos</h1>
    <p className="intro">Revisa las solicitudes, coordina correcciones y prepara cada entrega.</p>
    <div className="actions"><button className="secondary compact" onClick={() => setAttempt(value => value + 1)}>Actualizar pedidos</button>
      <span className="hint">Actualización automática cada 5 segundos.</span></div>
    {error && <p className="error" role="alert">{error} {orders && 'Los datos mostrados pueden estar desactualizados.'}</p>}
    {!orders && !error && <p role="status">Consultando pedidos…</p>}
    {orders?.length === 0 && <div className="empty-state"><h2>Todavía no hay solicitudes</h2><p>Crea un pedido con un perfil de cliente y vuelve a este panel.</p></div>}
    {orders && orders.length > 0 && <>
      <label htmlFor="company-search">Buscar por código o nombre del contacto</label>
      <input id="company-search" value={search} onChange={event => setSearch(event.target.value)} placeholder="MON-… o nombre" />
      <div className="order-filters" role="group" aria-label="Filtrar por etapa">
        <button className="secondary compact" aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>Todos ({orders.length})</button>
        {groups.map(group => <button className="secondary compact" key={group.id} aria-pressed={filter === group.id} onClick={() => setFilter(group.id)}>
          {group.label} ({orders.filter(order => group.statuses.includes(order.status)).length})
        </button>)}
      </div>
      {groups.filter(group => filter === 'all' || filter === group.id).map(group => {
        const list = matching.filter(order => group.statuses.includes(order.status))
        return <section className="company-group" key={group.id}><h2>{group.label} <span className="muted">({list.length})</span></h2>
          {list.length === 0 ? <p className="hint">Sin pedidos en esta etapa{query ? ' para tu búsqueda' : ''}.</p> : <ul className="orders-list">{list.map(order => <li key={order.id}>
            <a href={`#pedido/${order.code}`}><div><strong>{order.code}</strong><p>{order.contact_name} · {order.items.map(item => item.product).join(', ')}</p>
              <span className="hint">Salida: {formatDate(order.scheduled_departure_at)}</span></div>
              <div className="order-list-status"><span className="status-tag">{statusLabel(order)}</span><span>Revisar pedido →</span></div>
            </a></li>)}</ul>}
        </section>
      })}
    </>}
  </section>
}

function CompanyDetail({ actor, code }: { actor: DemoActor; code: string }) {
  const { order, setOrder, error, refresh } = useDemoOrder(actor, code, true)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [message, setMessage] = useState('')
  const [note, setNote] = useState('')
  const inFlight = useRef(false)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  async function perform(operation: () => Promise<Order>, success: string) {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true); setActionError(''); setMessage('')
    try {
      const value = await operation()
      if (mounted.current) {
        setOrder(current => !current || value.revision >= current.revision ? value : current)
        setMessage(success); setNote('')
      }
    } catch (failure) {
      if (mounted.current) {
        setActionError(failure instanceof Error ? failure.message : 'No pudimos guardar el cambio.')
        refresh()
      }
    } finally {
      inFlight.current = false
      if (mounted.current) setBusy(false)
    }
  }
  function act(action: CompanyAction, success: string, reason = '') {
    if (order) void perform(() => demoApi.companyAct(actor.id, order, action, reason), success)
  }
  if (!order) return <section className="panel"><h1>Detalle del pedido</h1>
    {error ? <p className="error" role="alert">{error}</p> : <p role="status">Consultando pedido…</p>}
    <div className="actions"><button className="secondary compact" onClick={refresh}>Reintentar</button><a href="#pedidos">Volver al panel</a></div>
  </section>
  const received = order.status === 'recibido'
  const needsCorrection = order.correction_status === 'requested'
  const canSchedule = ['confirmado', 'preparando', 'listo_para_salir'].includes(order.status)
  return <section className="panel" aria-busy={busy}>
    <a href="#pedidos">← Volver al panel</a><p className="eyebrow">Revisión de empresa</p><h1>{order.code}</h1>
    <p className="status-tag">{statusLabel(order)}</p>
    {error && <p className="error" role="alert">{error} La información puede estar desactualizada.</p>}
    <button className="text-button" disabled={busy} onClick={refresh}>Actualizar detalle</button>
    {actionError && <p className="error" role="alert">{actionError}</p>}
    {message && <p className="info" role="status">{message}</p>}
    {order.correction_status !== 'none' && <p className="info preserve-lines"><strong>{needsCorrection ? 'Esperando al cliente' : order.correction_status === 'resubmitted' ? 'Cambios recibidos: revisa el detalle antes de confirmar' : 'Corrección resuelta al confirmar'}.</strong><br />Última solicitud: {order.correction_note}</p>}
    <OrderSummary data={order} />
    <OrderIssues order={order} />
    <DeliveryReceipt order={order} />
    <ThirdPartyDetails order={order} />
    {order.third_party && <p><a href="#terceros">Gestionar servicio por tercero →</a></p>}
    {order.needs_reschedule && <p><a href="#viajes">Gestionar reprogramación desde el viaje →</a></p>}
    {order.location && <><h3>Punto de entrega</h3><LocationMap value={order.location} /></>}
    <section className="company-controls"><h2>Revisión y preparación</h2>
      <fieldset disabled={busy || Boolean(error)}>
        {received && !needsCorrection && <>
          <button type="button" onClick={() => act('confirm', 'Pedido confirmado. Ya puedes programar sus fechas e iniciar la preparación.')}>Confirmar pedido</button>
          <form className="correction-request" onSubmit={event => { event.preventDefault(); act('request_correction', 'Solicitud enviada. El cliente verá qué debe corregir.', note.trim()) }}>
            <label htmlFor="correction-note">¿Qué debe corregir el cliente?</label>
            <textarea id="correction-note" required maxLength={1000} rows={3} value={note} onChange={event => setNote(event.target.value)} />
            <button className="secondary compact" disabled={!note.trim()} type="submit">Solicitar corrección</button>
          </form>
        </>}
        {needsCorrection && <p>La confirmación queda pendiente hasta que el cliente envíe su corrección.</p>}
        {order.status === 'confirmado' && <button onClick={() => act('start_preparation', 'Preparación iniciada.')}>Iniciar preparación</button>}
        {order.status === 'preparando' && <>
          {!order.scheduled_departure_at && <p className="info">Programa la salida para poder marcar el pedido como listo.</p>}
          <button disabled={!order.scheduled_departure_at} onClick={() => act('mark_ready', 'Pedido listo para salir. Ya puedes asignarlo desde Planificar entregas.')}>Marcar listo para salir</button>
        </>}
        {order.status === 'listo_para_salir' && <p>Preparación completada. {order.third_party ? `Entrega por ${order.third_party.partner.name}.` : order.assigned_truck_name ? `Asignado a ${order.assigned_truck_name}.` : 'Pendiente de asignar transporte.'} <a href={order.third_party ? '#terceros' : '#planificacion'}>Gestionar transporte →</a>{!order.assigned_truck_id && !order.third_party && <> · <a href="#terceros">Solicitar un aliado →</a></>}</p>}
      </fieldset>
    </section>
    <dl className="delivery-facts"><div><dt>Salida programada</dt><dd>{formatDate(order.scheduled_departure_at)}</dd></div>
      <div><dt>Entrega estimada</dt><dd>{formatDate(order.estimated_delivery_at, 'Por estimar')}</dd></div></dl>
    {order.trip_id ? <p className="info">{order.status === 'entregado' ? `Entrega registrada por ${order.assigned_driver_name}.` : `Viaje asignado a ${order.assigned_driver_name}. La carga y las fechas están bloqueadas.`} <a href="#viajes">Consultar viaje →</a></p> : order.assigned_truck_id && <p className="hint">Para cambiar el día de salida, retira primero este pedido del camión desde planificación. Puedes ajustar las horas del mismo día.</p>}
    {order.third_party && order.status !== 'entregado' && <p className="hint">Para ajustar fechas o cambiar de transporte, cancela primero el servicio antes de su despacho desde Entrega por tercero.</p>}
    {canSchedule && !order.trip_id && !order.third_party && <ScheduleForm key={`${order.scheduled_departure_at}:${order.estimated_delivery_at}`} order={order} disabled={busy || Boolean(error)} onSave={(departure, delivery) => {
      void perform(() => demoApi.schedule(actor.id, order, departure, delivery), 'Fechas guardadas y visibles para el cliente.')
    }} />}
    <OrderHistory order={order} />
  </section>
}

// Los campos se etiquetan explícitamente en hora de Guatemala (UTC−6).
function localDateInput(value: string | null) {
  return value ? new Date(new Date(value).getTime() - 6 * 3600000).toISOString().slice(0, 16) : ''
}

function ScheduleForm({ order, disabled, onSave }: {
  order: Order; disabled: boolean; onSave: (departure: string, delivery: string | null) => void
}) {
  const [departure, setDeparture] = useState(() => localDateInput(order.scheduled_departure_at))
  const [delivery, setDelivery] = useState(() => localDateInput(order.estimated_delivery_at))
  const [error, setError] = useState('')
  function save(event: FormEvent) {
    event.preventDefault()
    const departureDate = new Date(`${departure}-06:00`)
    const deliveryDate = delivery ? new Date(`${delivery}-06:00`) : null
    if (!Number.isFinite(departureDate.getTime()) || departureDate.getTime() <= Date.now()) {
      setError('La salida debe tener una fecha y hora futuras.'); return
    }
    if (deliveryDate && (!Number.isFinite(deliveryDate.getTime()) || deliveryDate < departureDate)) {
      setError('La entrega estimada debe ser igual o posterior a la salida.'); return
    }
    setError('')
    onSave(departureDate.toISOString(), deliveryDate?.toISOString() || null)
  }
  return <form className="schedule-form" onSubmit={save}><h2>Programar fechas</h2>
    <p className="hint">Hora de Guatemala (UTC−6). La fecha de entrega es una estimación y puede quedar pendiente.</p>
    <fieldset disabled={disabled}><div className="field-grid">
      <div><label htmlFor="departure">Salida programada</label><input type="datetime-local" id="departure" required value={departure} onChange={event => { setDeparture(event.target.value); setError('') }} /></div>
      <div><label htmlFor="delivery">Entrega estimada (opcional)</label><input type="datetime-local" id="delivery" value={delivery} onChange={event => { setDelivery(event.target.value); setError('') }} /></div>
    </div><button type="submit" className="secondary compact">Guardar fechas</button></fieldset>
    {error && <p className="error" role="alert">{error}</p>}
  </form>
}
