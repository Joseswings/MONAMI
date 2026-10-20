import { useState } from 'react'
import { demoApi } from '../api'
import type { DemoActor, Trip, TripStop } from '../api'
import { useDemoAction } from './useDemoAction'

export default function DeliveryConfirmation({ actor, trip, stop, disabled, onChanged }: {
  actor: DemoActor; trip: Trip; stop: TripStop; disabled: boolean; onChanged: (trip?: Trip) => void
}) {
  const [note, setNote] = useState('')
  const action = useDemoAction()
  return <form className="delivery-confirmation" aria-busy={action.busy} onSubmit={event => {
    event.preventDefault()
    void action.perform(async () => {
      try {
        const value = await demoApi.deliverOrder(actor.id, trip, stop, note.trim())
        if (action.isMounted()) onChanged(value)
      } catch (failure) { if (action.isMounted()) onChanged(); throw failure }
    }, 'Entrega confirmada. Empresa y cliente verán la fecha registrada.')
  }}><fieldset disabled={disabled || action.busy || Boolean(trip.active_incident_id)}>
    <label htmlFor={`delivery-note-${stop.code}`}>Nota de entrega (opcional)</label>
    <textarea id={`delivery-note-${stop.code}`} rows={2} maxLength={1000} value={note} onChange={event => setNote(event.target.value)} />
    <p className="hint">Confirma después de entregar este pedido. La acción cierra su seguimiento y queda registrada en el historial.</p>
    <button type="submit" className="compact">Confirmar pedido entregado</button>
  </fieldset>
    {trip.active_incident_id && <p className="hint">La empresa debe resolver el incidente de ruta antes de confirmar entregas.</p>}
    {action.error && <p className="error" role="alert">{action.error} Actualiza y revisa antes de reintentar.</p>}
  </form>
}
