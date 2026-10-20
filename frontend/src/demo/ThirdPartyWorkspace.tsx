import { useState } from 'react'
import { demoApi } from '../api'
import type { DemoActor, DeliveryPartner, Order, ThirdPartyAction, ThirdPartyService } from '../api'
import { formatDate } from './OrderParts'
import { useDemoAction } from './useDemoAction'
import { useLiveData } from './useLiveData'

const labels = { pendiente_aceptacion: 'Pendiente de aceptación', confirmado: 'Servicio confirmado', en_camino: 'En camino', cancelado: 'Servicio cancelado', entregado: 'Entregado · Confirmado por empresa (simulado)' }

export default function ThirdPartyWorkspace({ actor }: { actor: DemoActor }) {
  const { data, error, refresh } = useLiveData(actor.id, () => demoApi.thirdParty(actor.id))
  const [query, setQuery] = useState('')
  const [onlyUncovered, setOnlyUncovered] = useState(false)
  const candidates = data?.candidates.filter(item => (!onlyUncovered || !item.compatible_trucks.length) && `${item.order.code} ${item.order.contact_name}`.toLowerCase().includes(query.trim().toLowerCase())) || []
  return <section className="panel">
    <p className="eyebrow">Empresa · Transporte externo</p><h1>Entrega por tercero</h1>
    <p className="intro">Revisa qué pedidos no cubre la flota y coordina su entrega con una paquetería aliada.</p>
    <p className="info">Aliados y contactos ficticios. La solicitud y la aceptación se simulan aquí; no se envían mensajes ni se consulta una paquetería real.</p>
    <button className="secondary compact" onClick={refresh}>Actualizar servicios</button>
    {error && <p className="error" role="alert">{error} Los datos pueden estar desactualizados.</p>}
    {!data && !error && <p role="status">Consultando aliados y pedidos…</p>}
    {data && <>
      <h2>Aliados de prueba</h2><div className="partner-grid">{data.partners.map(partner => <PartnerCard key={partner.id} partner={partner} />)}</div>
      <h2>Pedidos listos sin transporte ({data.candidates.length})</h2>
      <p className="hint">La evaluación considera capacidad, día de salida y reservas de camiones. Cobertura geográfica, disponibilidad del aliado y tarifas requieren decisión de empresa.</p>
      <label htmlFor="third-party-search">Buscar por código o contacto</label><input id="third-party-search" value={query} onChange={event => setQuery(event.target.value)} />
      <label className="coverage-filter"><input type="checkbox" checked={onlyUncovered} onChange={event => setOnlyUncovered(event.target.checked)} /> Solo sin camión compatible</label>
      {!candidates.length && <p className="info">Sin pedidos para estos filtros. Prepara un pedido o libera su asignación de flota para solicitar un aliado.</p>}
      {candidates.map(candidate => <RequestForm key={candidate.order.code} actor={actor} order={candidate.order} partners={data.partners} assessment={candidate.fleet_assessment} compatible={candidate.compatible_trucks} disabled={Boolean(error)} onChanged={refresh} />)}
      <h2>Servicios abiertos ({data.services.filter(order => order.status !== 'entregado').length})</h2>
      {!data.services.length && <p className="hint">Todavía no hay solicitudes activas de entrega por tercero.</p>}
      {data.services.filter(order => order.status !== 'entregado').map(order => <ServiceControls key={order.code} actor={actor} order={order} disabled={Boolean(error)} onChanged={refresh} />)}
      <h2>Entregas por tercero cerradas</h2>
      {data.services.filter(order => order.status === 'entregado').map(order => <details key={order.code} className="third-party-card"><summary>{order.code} · {order.third_party?.partner.name} · Entregado el {formatDate(order.delivered_at)}</summary><a href={`#pedido/${order.code}`}>Ver pedido entregado →</a><ThirdPartyDetails order={order} /><ServiceHistory service={order.third_party!} /></details>)}
      <p className="hint">Actualización cada 5 segundos. Al 100% el pedido sigue En camino hasta que empresa confirme explícitamente la entrega simulada.</p>
    </>}
  </section>
}

function PartnerCard({ partner }: { partner: DeliveryPartner }) {
  const [message, setMessage] = useState('')
  return <article className="partner-card"><h3>{partner.name}</h3><p>{partner.contact_name}<br /><span className="contact-address">{partner.contact_email}</span></p>
    <p className="hint">{partner.instructions}</p><button className="secondary compact" onClick={async () => {
      try { await navigator.clipboard.writeText(partner.contact_email); setMessage('Contacto ficticio copiado. No se envió ningún mensaje.') }
      catch { setMessage('Selecciona y copia el correo mostrado en esta tarjeta.') }
    }}>Copiar contacto</button>{message && <p className="hint" role="status">{message}</p>}
  </article>
}

function RequestForm({ actor, order, partners, assessment, compatible, disabled, onChanged }: {
  actor: DemoActor; order: Order; partners: DeliveryPartner[]; assessment: string; compatible: string[]; disabled: boolean; onChanged: () => void
}) {
  const action = useDemoAction()
  const [partnerId, setPartnerId] = useState('')
  const [reason, setReason] = useState('')
  return <form className="third-party-card" aria-busy={action.busy} onSubmit={event => {
    event.preventDefault()
    void action.perform(async () => {
      try { await demoApi.requestThirdParty(actor.id, order, partnerId, reason.trim()) }
      finally { if (action.isMounted()) onChanged() }
    }, 'Solicitud simulada registrada. Pendiente de aceptación.')
  }}><h3><a href={`#pedido/${order.code}`}>{order.code}</a> · {order.contact_name}</h3>
    <p>{order.items.map(item => `${item.product} × ${item.quantity}`).join(', ')} · {order.address}</p>
    <p>Salida: {formatDate(order.scheduled_departure_at)}</p><p className={compatible.length ? 'hint' : 'info'}>{assessment}</p>
    {compatible.length > 0 && <p className="hint">Capacidad compatible en: {compatible.join(', ')}. Puedes elegir tercero por una razón operativa.</p>}
    <fieldset disabled={disabled || action.busy}>
      <label htmlFor={`partner-${order.code}`}>Aliado</label><select id={`partner-${order.code}`} required value={partnerId} onChange={event => setPartnerId(event.target.value)}>
        <option value="">Seleccionar aliado</option>{partners.map(partner => <option key={partner.id} value={partner.id}>{partner.name}</option>)}
      </select>
      <label htmlFor={`coverage-${order.code}`}>¿Por qué la flota propia no cubre este pedido?</label><textarea id={`coverage-${order.code}`} required rows={2} maxLength={1000} value={reason} onChange={event => setReason(event.target.value)} />
      <button type="submit" className="compact" disabled={!partnerId || !reason.trim()}>Simular solicitud de servicio</button>
    </fieldset>
    {action.error && <p className="error" role="alert">{action.error} Actualiza y revisa antes de reintentar.</p>}
  </form>
}

function ServiceControls({ actor, order, disabled, onChanged }: { actor: DemoActor; order: Order; disabled: boolean; onChanged: () => void }) {
  const action = useDemoAction()
  const [note, setNote] = useState('')
  const [copyMessage, setCopyMessage] = useState('')
  const service = order.third_party!
  function act(command: ThirdPartyAction, message: string) {
    void action.perform(async () => {
      try { await demoApi.thirdPartyAct(actor.id, order, command, note.trim()); if (action.isMounted()) setNote('') }
      finally { if (action.isMounted()) onChanged() }
    }, message)
  }
  return <article className="third-party-card" aria-busy={action.busy}>
    <h3><a href={`#pedido/${order.code}`}>{order.code}</a> · {order.contact_name}</h3>
    <ThirdPartyDetails order={order} />
    <p className="preserve-lines">Motivo de cobertura: {service.reason}</p>
    <p>Salida programada: {formatDate(order.scheduled_departure_at)} · Entrega estimada: {formatDate(order.estimated_delivery_at, 'Por estimar')}</p>
    <p className="hint">La solicitud queda registrada en Monami. Puedes copiar un resumen para ensayar el contacto.</p>
    <button className="secondary compact" onClick={async () => {
      try {
        await navigator.clipboard.writeText(`Solicitud simulada ${service.reference}\nAliado: ${service.partner.name}\nContacto ficticio: ${service.partner.contact_email}\nPedido: ${order.code}\nDestino: ${order.address}\nSalida: ${formatDate(order.scheduled_departure_at)}\nProductos: ${order.items.map(item => `${item.product} x ${item.quantity}`).join(', ')}`)
        setCopyMessage('Resumen copiado. No se envió al aliado.')
      } catch { setCopyMessage('Puedes copiar los datos que se muestran en el servicio.') }
    }}>Copiar solicitud</button>{copyMessage && <p className="hint" role="status">{copyMessage}</p>}
    <fieldset disabled={disabled || action.busy}>
      <label htmlFor={`service-note-${order.code}`}>Nota de operación (obligatoria para cancelar)</label><textarea id={`service-note-${order.code}`} rows={2} maxLength={1000} value={note} onChange={event => setNote(event.target.value)} />
      <div className="actions">
        {service.status === 'pendiente_aceptacion' && <button className="compact" onClick={() => act('confirm', 'Aceptación del aliado simulada. Ya puedes despachar.')}>Simular aceptación del aliado</button>}
        {service.status === 'confirmado' && <button className="compact" onClick={() => act('dispatch', 'Despacho simulado. El cliente verá su pedido En camino.')}>Simular despacho por tercero</button>}
        {service.status === 'en_camino' && <button className="compact" disabled={service.progress_percent === 100} onClick={() => act('advance', 'Seguimiento simulado actualizado.')}>Simular avance +25%</button>}
        {service.status === 'en_camino' && <button className="compact" onClick={() => act('deliver', 'Entrega por tercero confirmada por empresa (simulada).')}>Confirmar entrega por tercero (simulada)</button>}
        {['pendiente_aceptacion', 'confirmado'].includes(service.status) && <button className="secondary compact" disabled={!note.trim()} onClick={() => act('cancel', 'Servicio cancelado. El pedido vuelve a estar disponible para planificar.')}>Cancelar servicio antes del despacho</button>}
      </div>
    </fieldset>
    {action.error && <p className="error" role="alert">{action.error} Actualiza y revisa antes de reintentar.</p>}
    {action.message && <p className="info" role="status">{action.message}</p>}
    <details><summary>Historial del servicio</summary><ServiceHistory service={service} /></details>
  </article>
}

export function ThirdPartyDetails({ order }: { order: Order }) {
  const service = order.third_party
  return <>
    {service && <section className="third-party-summary"><h3>Entrega por tercero · {service.partner.name}</h3>
      <p className="status-tag">{labels[service.status]}</p>
      <dl className="delivery-facts"><div><dt>Referencia de prueba</dt><dd>{service.reference}</dd></div>
        <div><dt>Contacto del aliado (ficticio)</dt><dd className="contact-address">{service.partner.contact_name}<br />{service.partner.contact_email}</dd></div>
        <div><dt>Solicitud registrada</dt><dd>{formatDate(service.requested_at)}</dd></div>
        {service.confirmed_at && <div><dt>Aceptación simulada</dt><dd>{formatDate(service.confirmed_at)}</dd></div>}
        {service.dispatched_at && <div><dt>Despacho simulado</dt><dd>{formatDate(service.dispatched_at)}</dd></div>}
        {service.delivered_at && <div><dt>Entrega confirmada por empresa</dt><dd>{formatDate(service.delivered_at)}</dd></div>}
      </dl>
      {service.status === 'en_camino' && <><label htmlFor={`third-progress-${order.code}`}>Avance simulado: {service.progress_percent}%</label><progress id={`third-progress-${order.code}`} max={100} value={service.progress_percent} /><p className="hint">Avance registrado manualmente por empresa. Sin ubicación GPS ni recorrido del aliado. El 100% no confirma la entrega.</p></>}
      {['pendiente_aceptacion', 'confirmado'].includes(service.status) && <p className="hint">El pedido permanece Listo para salir hasta registrar el despacho por tercero.</p>}
      {service.status === 'entregado' && <p className="delivery-receipt">Entrega simulada confirmada. El seguimiento de este pedido está cerrado.</p>}
    </section>}
    {order.third_party_history.length > 0 && <details className="third-party-archive"><summary>Servicios anteriores ({order.third_party_history.length})</summary>
      {order.third_party_history.map(item => <section key={item.id}><h4>{item.partner.name} · {item.reference} · {labels[item.status]}</h4><ServiceHistory service={item} /></section>)}
    </details>}
  </>
}

function ServiceHistory({ service }: { service: ThirdPartyService }) {
  return <ol className="attempt-history">{service.history.map((event, index) => <li key={index}><strong>{event.action}</strong><p className="hint">{formatDate(event.at)} · {event.actor_name}</p>{event.note && <p className="preserve-lines">{event.note}</p>}</li>)}</ol>
}
