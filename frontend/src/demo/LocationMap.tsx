import { useEffect, useRef, useState } from 'react'
import * as L from 'leaflet'
import type { Location } from '../api'
import 'leaflet/dist/leaflet.css'

export default function LocationMap({ value, onChange }: {
  value: Location | null; onChange?: (value: Location) => void
}) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const marker = useRef<L.CircleMarker | null>(null)
  const callback = useRef(onChange)
  const initial = useRef(value)
  const [tileError, setTileError] = useState(false)
  callback.current = onChange

  useEffect(() => {
    if (!container.current) return
    const center = initial.current
    const instance = L.map(container.current, { scrollWheelZoom: false }).setView(
      center ? [center.latitude, center.longitude] : [14.6349, -90.5069], 12,
    )
    const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(instance)
    tiles.on('tileerror', () => setTileError(true))
    instance.on('click', (event: L.LeafletMouseEvent) => {
      const point = event.latlng.wrap()
      callback.current?.({ latitude: Number(point.lat.toFixed(6)), longitude: Number(point.lng.toFixed(6)) })
    })
    map.current = instance
    return () => { instance.remove(); map.current = null; marker.current = null }
  }, [])

  useEffect(() => {
    const instance = map.current
    if (!instance) return
    if (marker.current) { marker.current.remove(); marker.current = null }
    if (value) {
      marker.current = L.circleMarker([value.latitude, value.longitude], {
        radius: 9, color: '#134e4a', fillColor: '#d6a34c', fillOpacity: 1, weight: 3,
      }).addTo(instance)
      instance.panTo([value.latitude, value.longitude])
    }
  }, [value])

  return <div>
    <div ref={container} className="location-map" role="region" aria-label="Mapa de ubicación de entrega" />
    <p className="hint">{onChange ? 'Pulsa el mapa para marcar tu ubicación. ' : ''}
      {tileError ? 'La cartografía no cargó; puedes ingresar las coordenadas debajo.' : 'La dirección no se localiza automáticamente.'}
    </p>
  </div>
}
