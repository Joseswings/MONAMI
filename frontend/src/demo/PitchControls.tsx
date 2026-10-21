import { useState } from 'react'
import { pitchApi } from '../api'
import type { DemoContext } from '../api'
import { useDemoAction } from './useDemoAction'

export function PitchAccess({ onAccess }: { onAccess: (context: DemoContext) => void }) {
  const action = useDemoAction()
  return <main><section className="card"><span className="brand">monami.</span><h1>Explora la demo</h1>
    <p>Un escenario preparado con datos ficticios para recorrer Monami desde cliente, empresa y conductor.</p>
    <form onSubmit={event => { event.preventDefault(); void action.perform(async () => {
      const context = await pitchApi.login()
      if (action.isMounted()) onAccess(context)
    }, '') }}><fieldset disabled={action.busy}>
      <button type="submit">{action.busy ? 'Entrando…' : 'Explorar demo'}</button>
    </fieldset></form>
    {action.error && <p className="error" role="alert">{action.error}</p>}
    <p className="hint">Acceso libre, sin clave. Al recargar, pulsa Explorar demo para volver a entrar; el escenario conserva sus datos.</p>
  </section></main>
}

export default function PitchControls({ context, onRefresh, onLogout }: { context: DemoContext; onRefresh: () => void; onLogout: () => void }) {
  const [open, setOpen] = useState(false)
  const [key, setKey] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const action = useDemoAction()
  return <section className="pitch-controls"><div className="actions"><strong>{context.scenario_name}</strong>
    <button className="text-button" onClick={onRefresh}>Actualizar escenario</button>
    <button className="text-button" onClick={() => setOpen(value => !value)}>Reiniciar presentación</button>
    <button className="text-button" disabled={action.busy} onClick={() => { void action.perform(async () => { try { await pitchApi.logout() } finally { onLogout() } }, '') }}>Salir de la demo</button>
  </div><p className="hint">Escenario compartido por los participantes. Usa únicamente datos ficticios. El progreso se conserva al reiniciar el servidor.</p>
    {open && <form onSubmit={event => { event.preventDefault(); void action.perform(async () => {
      await pitchApi.reset(key, context.scenario_generation!)
      if (action.isMounted()) { setKey(''); onRefresh() }
    }, 'Escenario restaurado.') }}><fieldset disabled={action.busy}>
      <p>Se reemplazarán los pedidos y viajes de esta presentación por el escenario inicial para todos los participantes.</p>
      <label htmlFor="pitch-reset">Clave del presentador</label><input id="pitch-reset" required type="password" maxLength={256} autoComplete="off" value={key} onChange={event => setKey(event.target.value)} />
      <label className="coverage-filter"><input type="checkbox" required checked={confirmed} onChange={event => setConfirmed(event.target.checked)} /> Quiero reiniciar el escenario compartido.</label>
      <button type="submit" className="secondary compact" disabled={!confirmed || !key}>Restaurar escenario inicial</button>
    </fieldset></form>}
    {action.error && <p className="error" role="alert">{action.error}</p>}
  </section>
}
