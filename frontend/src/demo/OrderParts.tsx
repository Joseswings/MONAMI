import { useEffect, useState } from 'react'
import { ApiError, demoApi } from '../api'
import type { DemoActor, Order } from '../api'

export const stages = [
  ['recibido', 'Recibido'], ['confirmado', 'Confirmado'], ['preparando', 'Preparando pedido'],
  ['listo_para_salir', 'Listo para salir'], ['en_camino', 'En camino'], ['entregado', 'Entregado'],
]

export function formatDate(value: string | null, fallback = 'Por programar') {
  return value ? new Intl.DateTimeFormat('es-GT', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Guatemala' }).format(new Date(value)) : fallback
}

export function statusLabel(order: Order) {
  if (order.status === 'entregado') return order.delivery_mode === 'tercero' ? 'Entregado · Entrega por tercero' : 'Entregado'
  if (order.needs_reschedule) return 'Con problema · Reprogramación pendiente'
  if (order.third_party) return order.third_party.status === 'pendiente_aceptacion' ? 'Entrega por tercero · Pendiente de aceptación' : order.third_party.status === 'confirmado' ? 'Entrega por tercero · Servicio confirmado' : 'Entrega por tercero · En camino'
  if (order.status === 'listo_para_salir' && order.delivery_attempts.some(attempt => attempt.status === 'reprogramado')) return 'Reprogramado · Listo para salir'
  if (order.correction_status === 'requested') return 'Corrección pendiente del cliente'
  if (order.correction_status === 'resubmitted') return 'Corrección enviada · Por revisar'
  return order.status === 'recibido' ? 'Pendiente de confirmación' : stages.find(([status]) => status === order.status)?.[1]
}

export function DeliveryReceipt({ order }: { order: Order }) {
  return order.status === 'entregado' ? <section className="delivery-receipt" role="status"><h2>Pedido entregado</h2>
    <p>Entrega confirmada el <strong>{formatDate(order.delivered_at)}</strong>.</p>
    <p className="hint">Registrada por {order.delivered_by}{order.delivery_mode === 'tercero' ? ' · Confirmación de tercero simulada por empresa.' : ' · Conductor asignado.'}</p>
    {order.delivery_note && <p className="preserve-lines">{order.delivery_note}</p>}
  </section> : null
}

export function OrderHistory({ order }: { order: Order }) {
  return <section className="order-history"><h2>Historial del pedido</h2><ol>
    {order.history.map((event, index) => <li key={index}><strong>{event.action}</strong>
      <span className="hint">{formatDate(event.at)} · {event.actor_name}</span>
      {event.note && <p className="preserve-lines">{event.note}</p>}
      {event.scheduled_departure_at && <p>Salida: {formatDate(event.scheduled_departure_at)}<br />Entrega estimada: {formatDate(event.estimated_delivery_at, 'Por estimar')}</p>}
    </li>)}
  </ol></section>
}

export function useOrderRoute() {
  function read() {
    const match = /^#pedido\/(MON-[a-f0-9]{8})$/i.exec(window.location.hash)
    return { code: match?.[1].toUpperCase() || '', planning: window.location.hash === '#planificacion', trips: window.location.hash === '#viajes', thirdParty: window.location.hash === '#terceros' }
  }
  const [route, setRoute] = useState(read)
  useEffect(() => {
    const sync = () => setRoute(read())
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])
  return route
}

export function useDemoOrder(actor: DemoActor, code: string, company = false) {
  const [order, setOrder] = useState<Order | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    let sequence = 0
    const load = async () => {
      const ticket = ++sequence
      try {
        const value = await (company ? demoApi.companyGet(actor.id, code) : demoApi.get(actor.id, code))
        if (active && ticket === sequence) {
          setOrder(current => !current || value.revision >= current.revision ? value : current)
          setError('')
        }
      } catch (failure) {
        if (active && ticket === sequence) {
          setError(failure instanceof Error ? failure.message : 'No pudimos consultar el pedido.')
          if (failure instanceof ApiError && failure.status === 404) setOrder(null)
        }
      }
    }
    void load()
    const timer = window.setInterval(load, 5000)
    return () => { active = false; window.clearInterval(timer) }
  }, [actor.id, code, company, attempt])
  return { order, setOrder, error, refresh: () => setAttempt(value => value + 1) }
}
