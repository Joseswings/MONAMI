import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import Access from './Access'
import { ApiError, demoApi } from './api'
import type { DemoContext } from './api'
import DemoApp from './demo/DemoApp'
import { PitchAccess } from './demo/PitchControls'
import './styles.css'

function App() {
  const [context, setContext] = useState<DemoContext | null>(null)
  const [mode, setMode] = useState<'loading' | 'demo' | 'pitch' | 'database' | 'error'>('loading')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    setMode('loading')
    demoApi.context().then(value => {
      if (active) { setContext(value); setMode('demo') }
    }).catch(error => {
      if (active) setMode(error instanceof ApiError && error.status === 401 ? 'pitch' : error instanceof ApiError && error.status === 404 ? 'database' : 'error')
    })
    return () => { active = false }
  }, [attempt])
  useEffect(() => {
    const expired = () => { setContext(null); setMode('pitch') }
    window.addEventListener('monami:pitch-expired', expired)
    return () => window.removeEventListener('monami:pitch-expired', expired)
  }, [])
  useEffect(() => {
    if (mode !== 'demo' || !context?.scenario_generation) return
    let active = true
    const timer = window.setInterval(() => { void demoApi.context().then(value => {
      if (active) setContext(current => {
        if (current?.scenario_generation !== value.scenario_generation) window.location.hash = '#pedidos'
        return value
      })
    }).catch(() => { /* Las vistas muestran sus errores y la sesión vencida tiene su propio aviso. */ }) }, 15000)
    return () => { active = false; window.clearInterval(timer) }
  }, [mode, context?.scenario_generation])
  if (mode === 'pitch') return <PitchAccess onAccess={value => { setContext(value); setMode('demo') }} />
  if (mode === 'demo' && context) return <DemoApp key={context.scenario_generation || 'local'} context={context} onRefresh={() => { window.location.hash = '#pedidos'; setAttempt(value => value + 1) }} onLogout={() => { setContext(null); setMode('pitch') }} />
  if (mode === 'database') return <Access />
  return <main><div className="card"><span className="brand">monami.</span>
    {mode === 'loading' ? <p role="status">Conectando con Monami…</p> : <>
      <h1>No pudimos conectar</h1><p>Comprueba que FastAPI esté encendido y vuelve a intentar.</p>
      <button onClick={() => setAttempt(value => value + 1)}>Reintentar</button>
    </>}
  </div></main>
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
