import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api, ApiError } from './api'
import type { Identity } from './api'
import './styles.css'

interface Session {
  token: string
  expiresAt: number
  identity: Identity
}

export default function Access() {
  const [session, setSession] = useState<Session | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [companyName, setCompanyName] = useState('')

  useEffect(() => {
    if (!session) return
    const timer = window.setTimeout(() => {
      setSession(null)
      setCompanyName('')
      setNotice('Tu sesión venció. Inicia sesión de nuevo.')
    }, Math.max(0, session.expiresAt - Date.now()))
    return () => window.clearTimeout(timer)
  }, [session])

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const fields = new FormData(form)
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const result = await api.login(String(fields.get('email')), String(fields.get('password')))
      const identity = await api.me(result.access_token)
      setSession({ token: result.access_token, expiresAt: Date.parse(result.expires_at), identity })
      form.reset()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'No pudimos iniciar sesión.')
    } finally {
      setBusy(false)
    }
  }

  async function logout() {
    if (!session) return
    setBusy(true)
    setError('')
    try {
      await api.logout(session.token)
      setSession(null)
      setCompanyName('')
      setNotice('Sesión cerrada.')
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) {
        setSession(null)
        setCompanyName('')
      } else {
        setError('No pudimos cerrar la sesión en el servidor. Intenta de nuevo.')
      }
    } finally {
      setBusy(false)
    }
  }

  async function checkCompany() {
    if (!session) return
    setBusy(true)
    setError('')
    try {
      const company = await api.company(session.token)
      setCompanyName(company.name)
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) {
        setSession(null)
        setCompanyName('')
        setNotice('Tu sesión ya no es válida. Inicia sesión de nuevo.')
      } else {
        setError(failure instanceof Error ? failure.message : 'No pudimos consultar la empresa.')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <main>
      <header><span className="brand">monami<span className="brand-dot">.</span></span>
        <span className="badge">Demo · Hito 1</span></header>
      <section className="card" aria-labelledby="heading" aria-busy={busy}>
        <p className="eyebrow">Coordinación logística</p>
        <h1 id="heading">{session ? `Hola, ${session.identity.name}` : 'Tu operación, conectada.'}</h1>
        {!session ? <>
          <p className="intro">Inicia sesión con tu cuenta de demostración.</p>
          <form onSubmit={login}>
            <label htmlFor="email">Correo electrónico</label>
            <input id="email" name="email" type="email" autoComplete="username" required
              maxLength={254} disabled={busy} />
            <label htmlFor="password">Contraseña</label>
            <input id="password" name="password" type="password" autoComplete="current-password"
              required maxLength={1024} disabled={busy} />
            <button disabled={busy} type="submit">{busy ? 'Conectando…' : 'Iniciar sesión'}</button>
          </form>
        </> : <>
          <p className="intro">Tu sesión está activa.</p>
          <dl>
            <dt>Correo</dt><dd>{session.identity.email}</dd>
            <dt>Empresa</dt><dd>{session.identity.organization.name}</dd>
            <dt>Rol</dt><dd className="role">{session.identity.role}</dd>
          </dl>
          {session.identity.role === 'empresa' && <>
            <button type="button" disabled={busy} onClick={checkCompany}>
              {busy ? 'Consultando…' : 'Consultar empresa'}
            </button>
            {companyName && <p role="status">Empresa verificada: {companyName}</p>}
          </>}
          <button className="secondary" type="button" disabled={busy} onClick={logout}>Cerrar sesión</button>
        </>}
        {error && <p className="error" role="alert">{error}</p>}
        {notice && <p className="notice" role="status">{notice}</p>}
      </section>
      <footer>Base de acceso · La gestión de pedidos se incorporará en el siguiente hito.</footer>
    </main>
  )
}

