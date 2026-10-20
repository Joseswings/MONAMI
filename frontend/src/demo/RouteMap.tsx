import { useEffect, useRef, useState } from 'react'
import * as L from 'leaflet'
import type { Location, PlannedStop } from '../api'
import 'leaflet/dist/leaflet.css'

export default function RouteMap({ depot, stops, vehiclePosition, routePoints, alternativePoints, referencePoints, incidentPosition }: {
  depot: Location; stops: PlannedStop[]; vehiclePosition?: Location | null
  routePoints?: (Location | null)[]; alternativePoints?: Location[]; referencePoints?: (Location | null)[]; incidentPosition?: Location | null
}) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const layers = useRef<L.LayerGroup | null>(null)
  const [tileError, setTileError] = useState(false)
  const geometry = JSON.stringify({ depot, stops, vehiclePosition, routePoints, alternativePoints, referencePoints, incidentPosition })

  useEffect(() => {
    if (!container.current) return
    const instance = L.map(container.current, { scrollWheelZoom: false }).setView([depot.latitude, depot.longitude], 12)
    const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(instance)
    tiles.on('tileerror', () => setTileError(true))
    map.current = instance
    layers.current = L.layerGroup().addTo(instance)
    return () => { instance.remove(); map.current = null; layers.current = null }
  }, [])

  useEffect(() => {
    const instance = map.current, group = layers.current
    if (!instance || !group) return
    group.clearLayers()
    const origin: L.LatLngTuple = [depot.latitude, depot.longitude]
    const bounds: L.LatLngTuple[] = [origin]
    let previous: L.LatLngTuple | null = origin
    function draw(points: (Location | null)[], color: string, dash: string, weight: number) {
      let segment: L.LatLngTuple[] = []
      function flush() { if (segment.length > 1) L.polyline(segment, { color, weight, dashArray: dash }).addTo(group!); segment = [] }
      for (const point of points) {
        if (!point) { flush(); continue }
        const coordinate: L.LatLngTuple = [point.latitude, point.longitude]
        bounds.push(coordinate); segment.push(coordinate)
      }
      flush()
    }
    if (referencePoints) draw(referencePoints, '#8a9099', '4 8', 2)
    if (routePoints) draw(routePoints, '#145b4e', '8 7', 3)
    if (alternativePoints) draw(alternativePoints, '#bd6300', '10 5', 4)
    L.marker(origin, { icon: L.divIcon({ className: 'route-pin depot-pin', html: 'B', iconSize: [30, 30], iconAnchor: [15, 15] }) })
      .bindTooltip('Bodega de prueba').addTo(group)
    for (const stop of stops) {
      if (!stop.location) { previous = null; continue }
      const point: L.LatLngTuple = [stop.location.latitude, stop.location.longitude]
      bounds.push(point)
      if (previous && !routePoints) L.polyline([previous, point], { color: '#145b4e', weight: 3, dashArray: '8 7' }).addTo(group)
      const label = document.createElement('span')
      label.textContent = `${stop.position}. ${stop.code} · ${stop.address}`
      L.marker(point, { icon: L.divIcon({ className: 'route-pin', html: String(stop.position), iconSize: [30, 30], iconAnchor: [15, 15] }) })
        .bindTooltip(label).addTo(group)
      previous = point
    }
    if (vehiclePosition) {
      const point: L.LatLngTuple = [vehiclePosition.latitude, vehiclePosition.longitude]
      bounds.push(point)
      L.circleMarker(point, { radius: 11, color: '#fff', weight: 3, fillColor: '#245fc2', fillOpacity: 1 })
        .bindTooltip('Posición simulada del vehículo').addTo(group)
    }
    if (incidentPosition) {
      const point: L.LatLngTuple = [incidentPosition.latitude, incidentPosition.longitude]
      bounds.push(point)
      L.circleMarker(point, { radius: 17, color: '#a92323', weight: 3, fillOpacity: 0.15 }).bindTooltip('Incidente simulado').addTo(group)
    }
    instance.fitBounds(L.latLngBounds(bounds), { padding: [35, 35], maxZoom: 14 })
  }, [geometry])

  return <div>
    <div ref={container} className="location-map route-map" role="region" aria-label="Mapa del recorrido simulado con paradas numeradas" />
    <p className="hint">B: bodega de prueba. Los números corresponden al orden de las paradas.
      {' '}El trazado une puntos en línea recta; no indica carreteras, tiempos ni navegación.
      {tileError && ' La cartografía no cargó; puedes revisar las direcciones y el orden en la lista.'}
      {stops.some(stop => !stop.location) && ' Faltan coordenadas: el mapa deja espacios en esos tramos.'}
      {vehiclePosition && ' El marcador azul representa una posición simulada, sin GPS real.'}
      {alternativePoints && ' Naranja: alternativa propuesta, pendiente de aprobación.'}
      {referencePoints && ' Gris: referencia del recorrido anterior. Verde: recorrido vigente.'}
      {incidentPosition && ' Rojo: incidente simulado.'}
    </p>
  </div>
}
