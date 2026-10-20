import { useEffect, useState } from 'react'
import { demoApi } from '../api'
import type { DemoActor, DemoContext, Order } from '../api'
import OrderForm, { OrderSummary } from './OrderForm'
import LocationMap from './LocationMap'
import CompanyWorkspace from './CompanyWorkspace'
import { CustomerTrackingPanel, DriverWorkspace } from './TripsWorkspace'
import { OrderIssues } from './TripIncidents'
import { ThirdPartyDetails } from './ThirdPartyWorkspace'
import PitchControls from './PitchControls'
import { DeliveryReceipt, formatDate, OrderHistory, stages, statusLabel, useDemoOrder } from './OrderParts'
function rememberActor(id: string | null) {
  try { if (id) sessionStorage.setItem('monami-demo-actor', id); else sessionStorage.removeItem('monami-demo-actor') } catch { /* La navegación funciona también sin almacenamiento. */ }
}
function rememberedActor() {
  try { return sessionStorage.getItem('monami-demo-actor') } catch { return null }
}
function currentRoute() {
  const hash = window.location.hash
  if (hash === '#nuevo') return { page: 'new', code: '' }
  const match = /^#pedido\/(MON-[a-f0-9]{8})$/i.exec(hash)
  return match ? { page: 'detail', code: match[1] } : { page: 'list', code: '' }
}

export default function DemoApp({ context, onRefresh, onLogout }: { context: DemoContext; onRefresh: () => void; onLogout: () => void }) {
  const [actorId, setActorId] = useState<string | null>(rememberedActor)
  const actor = context.actors.find(item => item.id === actorId)
  return <main className="demo-shell">
    <header><span className="brand">monami<span className="brand-dot">.</span></span>
      <div className="header-actions"><span className="badge">{context.storage === 'postgresql' ? 'Demo de pitch · Hito 9' : 'Simulación local · Hito 9'}</span>
        {actor && <button type="button" className="text-button" onClick={() => {
          rememberActor(null); setActorId(null); window.location.hash = ''
        }}>Cambiar rol</button>}</div>
    </header>
    {context.storage === 'postgresql' ? <PitchControls context={context} onRefresh={onRefresh} onLogout={onLogout} /> : <p className="demo-banner">Datos de prueba en memoria. Los pedidos se conservan al recargar la página y se borran al reiniciar FastAPI.</p>}
    {!actor ? <section className="role-intro">
      <p className="eyebrow">Bienvenido a {context.company}</p><h1>Cada entrega empieza contigo.</h1>
      <p className="intro">Elige desde dónde quieres explorar Monami. En este modo no necesitas contraseña.</p>
      <div className="role-grid">{context.actors.map(item => <button className="role-card" key={item.id} onClick={() => {
        rememberActor(item.id); window.location.hash = '#pedidos'; setActorId(item.id)
      }}>
        <span className="role-label">{item.role}</span><strong>{item.name}</strong><span>{item.email}</span>
        <span className="role-action">{item.role === 'cliente' ? 'Crear y consultar pedidos →' : item.role === 'empresa' ? 'Revisar y planificar entregas →' : 'Consultar carga y viaje →'}</span>
      </button>)}</div>
      <p className="hint">Los dos perfiles de cliente permiten comprobar que cada uno consulta sus propios pedidos. La selección de rol es una simulación, no autenticación.</p>
    </section> : actor.role === 'cliente' ? <CustomerWorkspace key={actor.id} actor={actor} /> : actor.role === 'empresa' ? <CompanyWorkspace key={actor.id} actor={actor} /> : <DriverWorkspace key={actor.id} actor={actor} />}
    <footer>Monami · EmpresaTest · Prototipo de coordinación logística</footer>
  </main>
}

function CustomerWorkspace({ actor }: { actor: DemoActor }) {
  const [route, setRoute] = useState(currentRoute)
  const [createdCode, setCreatedCode] = useState('')
  useEffect(() => {
    const sync = () => setRoute(currentRoute())
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])
  return <>
    <nav className="workspace-nav" aria-label="Pedidos del cliente">
      <div><strong>{actor.name}</strong><span className="hint">{actor.email}</span></div>
      <div className="nav-links"><a className={route.page !== 'new' ? 'selected' : ''} href="#pedidos">Mis pedidos</a>
        <a className={route.page === 'new' ? 'selected' : ''} href="#nuevo">+ Nuevo pedido</a></div>
    </nav>
    {route.page === 'new' ? <OrderForm actor={actor} onCancel={() => { window.location.hash = '#pedidos' }} onCreated={order => {
      setCreatedCode(order.code); window.location.hash = `#pedido/${order.code}`
    }} /> : route.page === 'detail' ? <OrderDetail key={route.code} actor={actor} code={route.code} newlyCreated={createdCode === route.code} />
      : <OrderList actor={actor} />}
  </>
}

function OrderList({ actor }: { actor: DemoActor }) {
  const [orders, setOrders] = useState<Order[] | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [search, setSearch] = useState('')
  useEffect(() => {
    let active = true
    const load = () => demoApi.list(actor.id).then(value => {
      if (active) { setOrders(value); setError('') }
    }).catch(failure => { if (active) setError(failure instanceof Error ? failure.message : 'No pudimos consultar tus pedidos.') })
    void load()
    const timer = window.setInterval(load, 5000)
    return () => { active = false; window.clearInterval(timer) }
  }, [actor.id, attempt])
  return <section className="panel">
    <p className="eyebrow">Tu espacio</p><h1>Mis pedidos</h1><p className="intro">Consulta tu solicitud y su etapa actual.</p>
    <form className="search-order" onSubmit={event => { event.preventDefault(); window.location.hash = `#pedido/${search.trim().toUpperCase()}` }}>
      <label htmlFor="order-code">Consultar por código</label><div className="actions">
        <input id="order-code" placeholder="MON-1234ABCD" required pattern="[Mm][Oo][Nn]-[a-fA-F0-9]{8}" value={search} onChange={event => setSearch(event.target.value)} />
        <button type="submit" className="compact">Consultar</button></div>
    </form>
    {error && <div className="error" role="alert">{error} <button className="text-button" onClick={() => setAttempt(a => a + 1)}>Reintentar</button></div>}
    {!orders && !error && <p role="status">Consultando tus pedidos…</p>}
    {orders?.length === 0 && !error && <div className="empty-state"><span className="empty-symbol" aria-hidden="true">↗</span><h2>Tu primera entrega comienza aquí</h2>
      <p>Crea una solicitud y consulta su seguimiento desde este espacio.</p><a className="button-link" href="#nuevo">Crear mi primer pedido</a></div>}
    {orders && orders.length > 0 && <ul className="orders-list">{orders.map(order => <li key={order.id}>
      <a href={`#pedido/${order.code}`}><div><strong>{order.code}</strong><p>{order.items.map(i => i.product).join(', ')}</p><span className="hint">{formatDate(order.created_at)}</span></div>
        <div className="order-list-status"><span className="status-tag">{statusLabel(order)}</span><span>Ver seguimiento →</span></div></a>
    </li>)}</ul>}
  </section>
}

function OrderDetail({ actor, code, newlyCreated }: { actor: DemoActor; code: string; newlyCreated: boolean }) {
  const { order, setOrder, error, refresh } = useDemoOrder(actor, code)
  const [correction, setCorrection] = useState<Order | null>(null)
  const [corrected, setCorrected] = useState(false)
  const [copyMessage, setCopyMessage] = useState('')
  if (correction) return <OrderForm actor={actor} correction={correction} onCancel={() => { setCorrection(null); refresh() }} onCreated={value => {
    setOrder(current => !current || value.revision >= current.revision ? value : current)
    setCorrection(null); setCorrected(true); refresh()
  }} />
  if (!order) return <section className="panel"><h1>Seguimiento del pedido</h1>
    {error ? <><p className="error" role="alert">{error}</p><button onClick={refresh}>Reintentar</button><p><a href="#pedidos">Volver a mis pedidos</a></p></> : <p role="status">Consultando el pedido…</p>}
  </section>
  const stage = stages.findIndex(([status]) => status === order.status)
  return <section className="panel">
    <p className="eyebrow">{newlyCreated ? 'Solicitud enviada' : 'Seguimiento'}</p>
    <h1>{newlyCreated ? '¡Recibimos tu pedido!' : 'Tu pedido, paso a paso'}</h1>
    <div className="receipt-code"><strong>{order.code}</strong><button type="button" className="text-button" onClick={async () => {
      try { await navigator.clipboard.writeText(order.code); setCopyMessage('Código copiado.') }
      catch { setCopyMessage('Puedes seleccionar y copiar el código que aparece arriba.') }
    }}>Copiar código</button></div>{copyMessage && <p className="hint" role="status">{copyMessage}</p>}
    <p className="intro">{order.status === 'recibido' ? 'EmpresaTest revisará tu solicitud antes de confirmar la entrega.' : 'Consulta la preparación y las fechas de tu entrega.'}</p>
    {error && <p className="error" role="alert">{error} La información mostrada puede estar desactualizada.</p>}
    <button className="text-button" onClick={refresh}>Actualizar seguimiento</button>
    {corrected && <p className="info" role="status">Corrección enviada. Conservas el mismo código de pedido.</p>}
    {order.correction_status === 'requested' && <div className="correction-notice"><h2>Tu pedido necesita una corrección</h2>
      <p className="preserve-lines">{order.correction_note}</p><button disabled={Boolean(error)} onClick={() => { setCorrected(false); setCorrection(order) }}>Corregir mi pedido</button></div>}
    {order.correction_status === 'resubmitted' && <p className="info">La empresa está revisando los cambios que enviaste.</p>}
    <ol className="tracker" aria-label="Etapas del pedido">{stages.map(([status, label], index) => <li key={status}
      className={index === stage ? 'active' : index < stage ? 'complete' : ''} aria-current={index === stage ? 'step' : undefined}>
      <span className="step-dot">{index + 1}</span><span>{label}</span></li>)}</ol>
    <p className="info">{statusLabel(order)}</p>
    <DeliveryReceipt order={order} />
    <OrderIssues order={order} />
    <ThirdPartyDetails order={order} />
    <dl className="delivery-facts"><div><dt>Solicitud recibida</dt><dd>{formatDate(order.created_at)}</dd></div>
      <div><dt>Salida programada</dt><dd>{formatDate(order.scheduled_departure_at)}</dd></div>
      <div><dt>Entrega estimada</dt><dd>{formatDate(order.estimated_delivery_at)}</dd></div>
      <div><dt>Transporte</dt><dd>{order.delivery_mode === 'tercero' ? 'Paquetería aliada' : order.delivery_mode === 'flota_propia' ? 'Flota propia' : 'Por asignar'}</dd></div>
      {order.assigned_truck_name && <div><dt>Camión asignado</dt><dd>{order.assigned_truck_name}</dd></div>}
      {order.actual_departure_at && <div><dt>Salida registrada</dt><dd>{formatDate(order.actual_departure_at)}</dd></div>}
    </dl>
    <h2>Detalle de tu solicitud</h2><OrderSummary data={order} />
    {order.location && <><h3>Punto de entrega</h3><LocationMap value={order.location} /></>}
    <OrderHistory order={order} />
    {order.trip_id && <CustomerTrackingPanel actor={actor} code={order.code} />}
    <a href="#pedidos">← Volver a mis pedidos</a>
  </section>
}
