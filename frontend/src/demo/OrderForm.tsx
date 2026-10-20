import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { demoApi } from '../api'
import type { DemoActor, Location, Order, OrderInput } from '../api'
import LocationMap from './LocationMap'

export function OrderSummary({ data }: { data: OrderInput }) {
  return <div className="summary-grid">
    <section><h3>Contacto</h3><p>{data.contact_name}<br />{data.contact_email}<br />{data.contact_phone}</p></section>
    <section><h3>Entrega</h3><p>{data.address}</p><p>{data.instructions || 'Sin instrucciones adicionales.'}</p>
      <p className="hint">{data.location ? `${data.location.latitude}, ${data.location.longitude}` : 'Sin punto en el mapa.'}</p>
    </section>
    <section className="wide"><h3>Productos solicitados</h3><ul className="product-list">
      {data.items.map((item, index) => <li key={index}><span>{item.product}</span><strong>{item.quantity} unidades</strong></li>)}
    </ul></section>
  </div>
}

export default function OrderForm({ actor, onCreated, onCancel, correction }: {
  actor: DemoActor; onCreated: (order: Order) => void; onCancel: () => void; correction?: Order
}) {
  const [data, setData] = useState<OrderInput>(correction ? {
    contact_name: correction.contact_name, contact_email: correction.contact_email, contact_phone: correction.contact_phone,
    items: correction.items.map(item => ({ ...item })), address: correction.address, location: correction.location,
    instructions: correction.instructions,
  } : { contact_name: actor.name, contact_email: actor.email,
    contact_phone: '', items: [{ product: '', quantity: 1 }], address: '', location: null, instructions: '' })
  const [review, setReview] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [coordinates, setCoordinates] = useState({ latitude: correction?.location ? String(correction.location.latitude) : '', longitude: correction?.location ? String(correction.location.longitude) : '' })
  const [locationError, setLocationError] = useState('')
  const key = useRef('')
  const inFlight = useRef(false)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  function change<K extends keyof OrderInput>(field: K, value: OrderInput[K]) {
    setData(previous => ({ ...previous, [field]: value }))
    setError('')
  }
  function markLocation(point: Location) {
    change('location', point)
    setCoordinates({ latitude: String(point.latitude), longitude: String(point.longitude) })
    setLocationError('')
  }
  function applyCoordinates() {
    const latitude = Number(coordinates.latitude), longitude = Number(coordinates.longitude)
    if (!coordinates.latitude.trim() || !coordinates.longitude.trim() || !Number.isFinite(latitude) ||
      !Number.isFinite(longitude) || Math.abs(latitude) > 85 || Math.abs(longitude) > 180) {
      setLocationError('Ingresa latitud entre -85 y 85 y longitud entre -180 y 180.')
      return
    }
    markLocation({ latitude, longitude })
  }
  function preview(event: FormEvent) {
    event.preventDefault()
    if (data.items.some(item => !item.product.trim()) || !data.contact_name.trim() || data.address.trim().length < 5) {
      setError('Completa el contacto, los productos y una dirección válida.')
      return
    }
    if ((coordinates.latitude || coordinates.longitude) && (!data.location ||
      Number(coordinates.latitude) !== data.location.latitude || Number(coordinates.longitude) !== data.location.longitude)) {
      setLocationError('Aplica las coordenadas ingresadas o bórralas antes de continuar.')
      return
    }
    key.current = crypto.randomUUID()
    setError('')
    setReview(true)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
  async function send() {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true); setError('')
    try {
      const order = correction ? await demoApi.correct(actor.id, correction.code, data, correction.revision)
        : await demoApi.create(actor.id, data, key.current)
      if (mounted.current) onCreated(order)
    }
    catch (failure) { if (mounted.current) setError(failure instanceof Error ? failure.message : 'No pudimos enviar el pedido.') }
    finally { inFlight.current = false; if (mounted.current) setBusy(false) }
  }

  return <section className="panel" aria-busy={busy}>
    <p className="eyebrow">{review ? 'Paso 2 de 2 · Revisión' : 'Paso 1 de 2 · Solicitud'}</p>
    <h1>{review ? 'Revisa tu pedido' : correction ? `Corregir ${correction.code}` : '¿Qué necesitas recibir?'}</h1>
    {correction && <p className="info preserve-lines"><strong>La empresa solicita:</strong> {correction.correction_note}</p>}
    <p className="intro">{review ? 'Comprueba los datos antes de enviarlos a EmpresaTest.' : 'Cuéntanos qué necesitas y dónde lo entregaremos.'}</p>
    {review ? <>
      <OrderSummary data={data} />
      <p className="info">{correction ? 'La empresa revisará tus cambios antes de confirmar el mismo pedido.' : 'Al enviarlo quedará pendiente de confirmación por la empresa.'}</p>
      <div className="actions"><button type="button" className="secondary" disabled={busy} onClick={() => setReview(false)}>Corregir datos</button>
        <button type="button" disabled={busy} onClick={send}>{busy ? 'Enviando…' : correction ? 'Enviar corrección' : 'Enviar pedido'}</button></div>
    </> : <form onSubmit={preview} className="order-form">
      <fieldset><legend>1. Tus datos de contacto</legend><div className="field-grid">
        <div><label htmlFor="contact-name">Nombre completo</label><input id="contact-name" required maxLength={160}
          autoComplete="name" value={data.contact_name} onChange={e => change('contact_name', e.target.value)} /></div>
        <div><label htmlFor="contact-email">Correo electrónico</label><input id="contact-email" type="email" required maxLength={254}
          autoComplete="email" value={data.contact_email} onChange={e => change('contact_email', e.target.value)} /></div>
        <div><label htmlFor="contact-phone">Teléfono</label><input id="contact-phone" type="tel" required minLength={5} maxLength={40}
          autoComplete="tel" placeholder="Ej. 5555 1234" value={data.contact_phone} onChange={e => change('contact_phone', e.target.value)} /></div>
      </div></fieldset>
      <fieldset><legend>2. Productos y cantidades</legend>
        {data.items.map((item, index) => <div className="item-row" key={index}>
          <div><label htmlFor={`product-${index}`}>Producto {index + 1}</label><input id={`product-${index}`} required maxLength={160}
            placeholder="Ej. Caja de vasos" value={item.product} onChange={e => change('items', data.items.map((p, i) => i === index ? { ...p, product: e.target.value } : p))} /></div>
          <div><label htmlFor={`quantity-${index}`}>Cantidad</label><input id={`quantity-${index}`} type="number" required min={1} max={100000} step={1}
            value={Number.isNaN(item.quantity) ? '' : item.quantity} onChange={e => change('items', data.items.map((p, i) => i === index ? { ...p, quantity: e.target.valueAsNumber } : p))} /></div>
          {data.items.length > 1 && <button type="button" className="text-button" onClick={() => change('items', data.items.filter((_, i) => i !== index))}>Quitar producto {index + 1}</button>}
        </div>)}
        {data.items.length < 20 && <button type="button" className="secondary compact" onClick={() => change('items', [...data.items, { product: '', quantity: 1 }])}>+ Agregar producto</button>}
      </fieldset>
      <fieldset><legend>3. Lugar de entrega</legend>
        <label htmlFor="address">Dirección completa</label><textarea id="address" required minLength={5} maxLength={500} rows={2}
          autoComplete="street-address" value={data.address} onChange={e => change('address', e.target.value)} placeholder="Calle, zona, municipio y departamento" />
        <p>Ubicación en el mapa <span className="muted">(opcional)</span></p>
        <LocationMap value={data.location} onChange={markLocation} />
        <details><summary>Ingresar coordenadas manualmente</summary><div className="field-grid">
          <div><label htmlFor="latitude">Latitud</label><input id="latitude" type="number" step="any" min={-85} max={85} value={coordinates.latitude}
            onChange={e => { setCoordinates({ ...coordinates, latitude: e.target.value }); setLocationError('') }} /></div>
          <div><label htmlFor="longitude">Longitud</label><input id="longitude" type="number" step="any" min={-180} max={180} value={coordinates.longitude}
            onChange={e => { setCoordinates({ ...coordinates, longitude: e.target.value }); setLocationError('') }} /></div>
        </div><button type="button" className="secondary compact" onClick={applyCoordinates}>Aplicar coordenadas</button></details>
        {data.location && <p className="hint">Punto seleccionado: {data.location.latitude}, {data.location.longitude} <button type="button" className="text-button" onClick={() => {
          change('location', null); setCoordinates({ latitude: '', longitude: '' }); setLocationError('')
        }}>Quitar ubicación</button></p>}
        {locationError && <p className="error" role="alert">{locationError}</p>}
        <label htmlFor="instructions">Referencias o instrucciones <span className="muted">(opcional)</span></label>
        <textarea id="instructions" maxLength={1000} rows={3} value={data.instructions} onChange={e => change('instructions', e.target.value)} placeholder="Ej. Portón verde; llamar antes de llegar" />
      </fieldset>
      <div className="actions"><button type="button" className="secondary" onClick={onCancel}>Cancelar</button><button type="submit">Revisar pedido</button></div>
    </form>}
    {error && <p className="error" role="alert">{error}</p>}
  </section>
}
