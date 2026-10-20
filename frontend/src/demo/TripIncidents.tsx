import { useState } from 'react'
import type { FormEvent } from 'react'
import { demoApi } from '../api'
import type { DemoActor, Order, RouteAlternative, Trip, TripStop } from '../api'
import { formatDate } from './OrderParts'
import RouteMap from './RouteMap'
import { useDemoAction } from './useDemoAction'

type Change = (trip?: Trip) => void

export function IncidentControls({ actor, trip, onChanged, disabled }: { actor: DemoActor; trip: Trip; onChanged: Change; disabled: boolean }) {
  const action = useDemoAction()
  const [kind, setKind] = useState<'bloqueo' | 'accidente'>('bloqueo')
  const [reason, setReason] = useState('')
  const [note, setNote] = useState('')
  const [delay, setDelay] = useState(30)
  const [preview, setPreview] = useState<RouteAlternative | null>(null)
  const incident = trip.incidents.find(item => item.id === trip.active_incident_id)
  const currentPreview = preview?.revision === trip.revision && preview.incident_id === incident?.id ? preview : null
  function resolve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const button = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null
    const decision = button?.value === 'alternativa' ? 'alternativa' : 'continuar'
    if (!incident || (decision === 'alternativa' && !currentPreview)) return
    void action.perform(async () => {
      const value = await demoApi.resolveIncident(actor.id, trip, incident.id, decision, delay, note.trim())
      if (action.isMounted()) { onChanged(value); setPreview(null); setNote('') }
    }, 'Incidente resuelto. El recorrido y las estimaciones ya están actualizados.')
  }
  return <section className="incident-section" aria-busy={action.busy}>
    {incident && <div className="incident-alert" role="alert"><h3>Avance pausado · {incident.kind}</h3><p className="preserve-lines">{incident.reason}</p><p className="hint">{formatDate(incident.reported_at)} · {incident.reported_by}</p></div>}
    {action.error && <p className="error" role="alert">{action.error} Actualiza el viaje antes de repetir la operación.</p>}
    {action.message && <p className="info" role="status">{action.message}</p>}
    {trip.status === 'en_camino' && !incident && trip.progress_percent < 100 && <form onSubmit={event => {
      event.preventDefault()
      void action.perform(async () => {
        const value = await demoApi.reportIncident(actor, trip, kind, reason.trim())
        if (action.isMounted()) { onChanged(value); setReason('') }
      }, 'Incidente registrado. La empresa recibió la alerta y el avance quedó pausado.')
    }}><fieldset disabled={disabled || action.busy}><legend>{actor.role === 'empresa' ? 'Simular incidente de ruta' : 'Reportar incidente de ruta'}</legend>
      <label htmlFor={`incident-kind-${trip.id}`}>Tipo</label><select id={`incident-kind-${trip.id}`} value={kind} onChange={event => setKind(event.target.value as typeof kind)}><option value="bloqueo">Bloqueo</option><option value="accidente">Accidente</option></select>
      <label htmlFor={`incident-reason-${trip.id}`}>Motivo</label><textarea id={`incident-reason-${trip.id}`} required maxLength={1000} value={reason} onChange={event => setReason(event.target.value)} />
      <button type="submit" className="secondary compact" disabled={!reason.trim()}>Registrar incidente simulado</button>
    </fieldset></form>}
    {incident && actor.role === 'empresa' && <form onSubmit={resolve}><fieldset disabled={disabled || action.busy}><legend>Resolver incidente</legend>
      <button type="button" className="secondary compact" onClick={() => {
        void action.perform(async () => {
          const value = await demoApi.alternative(actor.id, trip, incident.id)
          if (action.isMounted()) setPreview(value)
        }, 'Alternativa cargada para revisar. Todavía no cambia el recorrido.')
      }}>Proponer alternativa simulada</button>
      {preview && !currentPreview && <p className="error">El viaje cambió; genera otra propuesta antes de aprobar.</p>}
      {currentPreview && <RouteMap depot={trip.depot} stops={trip.stops.filter(stop => !trip.excluded_order_codes.includes(stop.code))} vehiclePosition={trip.position}
        routePoints={trip.route_points} alternativePoints={currentPreview.points} incidentPosition={incident.position} />}
      <p className="hint">La alternativa es un desvío geométrico de prueba. No verifica calles ni condiciones de tráfico.</p>
      <label htmlFor={`incident-delay-${trip.id}`}>Demora adicional simulada (minutos)</label><input id={`incident-delay-${trip.id}`} type="number" required min={0} max={1440} step={1} value={delay} onChange={event => setDelay(event.target.valueAsNumber)} />
      <label htmlFor={`incident-resolution-${trip.id}`}>Motivo de resolución</label><textarea id={`incident-resolution-${trip.id}`} required maxLength={1000} value={note} onChange={event => setNote(event.target.value)} />
      <div className="actions"><button type="submit" value="continuar" className="secondary compact" disabled={!note.trim()}>Resolver y continuar recorrido actual</button>
        <button type="submit" value="alternativa" className="compact" disabled={!currentPreview || !note.trim()}>Aprobar alternativa y actualizar estimaciones</button></div>
    </fieldset></form>}
    {trip.incidents.length > 0 && <details><summary>Historial de incidentes ({trip.incidents.length})</summary><ul className="incident-history">{trip.incidents.map(item => <li key={item.id}>
      <strong>{item.kind} · {item.status === 'abierto' ? 'En atención' : 'Resuelto'}</strong><p className="preserve-lines">{item.reason}</p><p className="hint">{formatDate(item.reported_at)} · {item.reported_by}</p>
      {item.resolved_at && <p className="preserve-lines">{item.resolution_note}<br />{formatDate(item.resolved_at)} · {item.resolved_by}<br />Demora adicional: {item.delay_minutes} minutos.</p>}
    </li>)}</ul></details>}
  </section>
}

export function DeliveryProblemForm({ actor, trip, stop, onChanged, disabled }: { actor: DemoActor; trip: Trip; stop: TripStop; onChanged: Change; disabled: boolean }) {
  const action = useDemoAction()
  const [reason, setReason] = useState('')
  return <form className="problem-form" onSubmit={event => {
    event.preventDefault()
    void action.perform(async () => {
      const value = await demoApi.reportProblem(actor.id, trip, stop, reason.trim())
      if (action.isMounted()) { onChanged(value); setReason('') }
    }, 'Problema registrado. La empresa podrá reprogramar este pedido.')
  }}><fieldset disabled={disabled || action.busy}><label htmlFor={`problem-${trip.id}-${stop.code}`}>Motivo del inconveniente de entrega</label>
    <textarea id={`problem-${trip.id}-${stop.code}`} required maxLength={1000} value={reason} onChange={event => setReason(event.target.value)} placeholder="Ej. No fue posible contactar al destinatario" />
    <button className="secondary compact" type="submit" disabled={!reason.trim()}>Marcar Con problema</button>
  </fieldset>{action.error && <p className="error" role="alert">{action.error} Actualiza el viaje.</p>}{action.message && <p className="info" role="status">{action.message}</p>}</form>
}

export function RescheduleForm({ actor, trip, stop, onChanged, disabled }: { actor: DemoActor; trip: Trip; stop: TripStop; onChanged: Change; disabled: boolean }) {
  const action = useDemoAction()
  const [departure, setDeparture] = useState('')
  const [delivery, setDelivery] = useState('')
  const [note, setNote] = useState('')
  return <form className="reschedule-form" onSubmit={event => {
    event.preventDefault()
    void action.perform(async () => {
      const next = new Date(`${departure}-06:00`), eta = delivery ? new Date(`${delivery}-06:00`) : null
      if (!Number.isFinite(next.getTime()) || next.getTime() <= Date.now()) throw new Error('La nueva salida debe ser futura.')
      if (eta && (!Number.isFinite(eta.getTime()) || eta < next)) throw new Error('La entrega estimada debe ser igual o posterior a la nueva salida.')
      await demoApi.reschedule(actor.id, trip, stop, next.toISOString(), eta?.toISOString() || null, note.trim())
      if (action.isMounted()) onChanged()
    }, 'Pedido reprogramado. Quedó Listo para salir y disponible para planificar otro viaje.')
  }}><fieldset disabled={disabled || action.busy}><legend>Reprogramar este pedido</legend>
    <p className="hint">Hora de Guatemala (UTC−6). Se retirará del viaje y del camión; conservará su código y el historial del intento.</p>
    <div className="field-grid"><div><label htmlFor={`reschedule-departure-${stop.code}`}>Nueva salida</label><input id={`reschedule-departure-${stop.code}`} type="datetime-local" required value={departure} onChange={event => setDeparture(event.target.value)} /></div>
      <div><label htmlFor={`reschedule-delivery-${stop.code}`}>Nueva entrega estimada (opcional)</label><input id={`reschedule-delivery-${stop.code}`} type="datetime-local" value={delivery} onChange={event => setDelivery(event.target.value)} /></div></div>
    <label htmlFor={`reschedule-note-${stop.code}`}>Motivo de reprogramación</label><textarea id={`reschedule-note-${stop.code}`} required maxLength={1000} value={note} onChange={event => setNote(event.target.value)} />
    <button type="submit" className="compact" disabled={!note.trim()}>Guardar reprogramación</button>
  </fieldset>{action.error && <p className="error" role="alert">{action.error} Actualiza el viaje antes de repetir.</p>}{action.message && <p className="info" role="status">{action.message}</p>}</form>
}

export function OrderIssues({ order }: { order: Order }) {
  return <>
    {order.needs_reschedule && <p className="incident-alert" role="alert">Hay un inconveniente con tu entrega. La empresa debe revisar su reprogramación.</p>}
    {order.delivery_attempts.length > 0 && <section className="delivery-attempts"><h2>Intentos de entrega</h2><ol>{order.delivery_attempts.map(attempt => <li key={attempt.id}>
      <strong>{attempt.status === 'pendiente' ? 'Con problema · En revisión' : 'Reprogramado'}</strong><p className="preserve-lines">{attempt.reason}</p>
      <p className="hint">Registrado: {formatDate(attempt.reported_at)} · {attempt.reported_by}<br />Salida del intento: {formatDate(attempt.actual_departure_at)}</p>
      {attempt.status === 'reprogramado' && <><p className="preserve-lines">{attempt.resolution_note}</p><p>Nueva salida: {formatDate(attempt.scheduled_departure_at)}<br />Entrega estimada: {formatDate(attempt.estimated_delivery_at, 'Por estimar')}</p></>}
    </li>)}</ol></section>}
  </>
}
