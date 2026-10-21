export type Role = 'cliente' | 'empresa' | 'conductor'

export interface Organization {
  id: string
  name: string
}

export interface Identity {
  id: string
  name: string
  email: string
  role: Role
  organization: Organization
}

interface LoginResult {
  access_token: string
  token_type: 'bearer'
  expires_at: string
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

const baseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
let pitchToken: string | null = null
let pitchGeneration: string | null = null

async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (pitchToken && (path.startsWith('/api/v1/demo/') || path.startsWith('/api/v1/pitch/'))) headers.set('Authorization', `Bearer ${pitchToken}`)
  if (pitchGeneration && path.startsWith('/api/v1/demo/')) headers.set('X-Pitch-Generation', pitchGeneration)
  let response: Response
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...options,
      headers,
      cache: 'no-store',
      credentials: 'omit',
      signal: AbortSignal.timeout(10000),
    })
  } catch {
    throw new ApiError(0, 'No pudimos conectar con Monami. Intenta de nuevo.')
  }
  if (!response.ok) {
    if (response.status === 401 && pitchToken && path !== '/api/v1/pitch/login') {
      pitchToken = null; pitchGeneration = null
      window.dispatchEvent(new Event('monami:pitch-expired'))
    }
    const messages: Record<number, string> = {
      401: 'Las credenciales o la sesión no son válidas.',
      403: 'Tu rol no tiene permiso para esta operación.',
      404: 'El recurso no está disponible para este perfil. Si reiniciaste FastAPI, los datos temporales se borraron.',
      409: 'La información cambió o no permite esta acción. Actualiza y revisa los datos.',
      422: 'Revisa los datos e intenta de nuevo.',
      503: 'El servicio de datos no está disponible. Intenta más tarde.',
    }
    let message = messages[response.status] || 'No pudimos completar la solicitud.'
    if (response.status === 409 && path.startsWith('/api/v1/demo/')) {
      try {
        const failure: unknown = await response.json()
        if (failure && typeof failure === 'object' && 'detail' in failure && typeof failure.detail === 'string' && failure.detail.length <= 500) message = failure.detail
      } catch { /* Conservar el mensaje general si la respuesta no es JSON. */ }
    }
    throw new ApiError(response.status, message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  login: (email: string, password: string) =>
    request<LoginResult>('/api/v1/auth/login', {
      method: 'POST', body: JSON.stringify({ email, password }),
    }),
  me: (token: string) => request<Identity>('/api/v1/me', {}, token),
  company: (token: string) => request<Organization>('/api/v1/company', {}, token),
  logout: (token: string) => request<void>('/api/v1/auth/logout', { method: 'POST' }, token),
}

export interface DemoActor { id: string; name: string; email: string; role: Role }
export interface DemoContext { mode: 'demo'; company: string; storage: 'memory' | 'postgresql'; actors: DemoActor[]; scenario_generation: string | null; scenario_name: string | null }
export interface Location { latitude: number; longitude: number }
export interface OrderItem { product: string; quantity: number }
export type OrderStatus = 'recibido' | 'confirmado' | 'preparando' | 'listo_para_salir' | 'en_camino' | 'entregado'
export interface OrderInput {
  contact_name: string
  contact_email: string
  contact_phone: string
  items: OrderItem[]
  address: string
  location: Location | null
  instructions: string
}
export interface Order extends OrderInput {
  id: string; code: string; customer_id: string; status: OrderStatus; created_at: string
  scheduled_departure_at: string | null; estimated_delivery_at: string | null
  delivered_at: string | null; delivery_mode: 'flota_propia' | 'tercero' | null
  delivered_by: string | null; delivery_note: string
  assigned_truck_id: string | null; assigned_truck_name: string | null
  trip_id: string | null; assigned_driver_name: string | null; actual_departure_at: string | null
  needs_reschedule: boolean
  delivery_attempts: DeliveryAttempt[]
  third_party: ThirdPartyService | null
  third_party_history: ThirdPartyService[]
  revision: number
  correction_status: 'none' | 'requested' | 'resubmitted' | 'resolved'
  correction_note: string
  history: { action: string; actor_name: string; at: string; note: string;
    scheduled_departure_at: string | null; estimated_delivery_at: string | null }[]
}

export type CompanyAction = 'confirm' | 'request_correction' | 'start_preparation' | 'mark_ready'

export interface DeliveryPartner {
  id: string; name: string; contact_name: string; contact_email: string; instructions: string
}
export interface ThirdPartyService {
  id: string; reference: string; partner: DeliveryPartner; reason: string
  status: 'pendiente_aceptacion' | 'confirmado' | 'en_camino' | 'cancelado' | 'entregado'
  requested_at: string; confirmed_at: string | null; dispatched_at: string | null; cancelled_at: string | null
  delivered_at: string | null
  progress_percent: number
  history: Order['history']
}
export interface ThirdPartySnapshot {
  revision: number; partners: DeliveryPartner[]
  candidates: { order: Order; fleet_assessment: string; compatible_trucks: string[] }[]
  services: Order[]
}
export type ThirdPartyAction = 'confirm' | 'dispatch' | 'advance' | 'cancel' | 'deliver'

export interface PlannedStop { position: number; code: string; address: string; location: Location | null; load_units: number }
export interface Truck {
  id: string; name: string; capacity: number; order_codes: string[]
  used_capacity: number; remaining_capacity: number; departure_date: string | null
  availability: 'disponible' | 'reservado' | 'completo' | 'viaje_asignado' | 'en_viaje'
  trip_id: string | null
  stops: PlannedStop[]; route_complete: boolean; straight_line_km: number | null
}
export interface FleetSnapshot {
  revision: number; depot: Location; depot_name: string; capacity_unit: string
  trucks: Truck[]; ready_orders: Order[]
}
export interface FleetSuggestion {
  revision: number; truck_id: string; departure_date: string; order_codes: string[]
  excluded: { code: string; reason: string }[]
}

export interface DeliveryAttempt {
  id: string; trip_id: string; reported_at: string; reported_by: string; reason: string
  actual_departure_at: string | null; status: 'pendiente' | 'reprogramado'
  resolved_at: string | null; resolved_by: string | null; resolution_note: string
  scheduled_departure_at: string | null; estimated_delivery_at: string | null
}
export type TripStatus = 'asignado' | 'carga_confirmada' | 'en_camino' | 'cancelado' | 'reprogramado' | 'completado'
export type DriverAction = 'confirm_load' | 'start_trip' | 'advance'
export interface TripStop extends PlannedStop {
  items: OrderItem[]; contact_name: string; contact_email: string; contact_phone: string; instructions: string
  order_revision: number; delivery_status: 'pendiente' | 'con_problema' | 'reprogramado' | 'entregado'; delivered_at: string | null
  problem_reason: string; rescheduled_departure_at: string | null; estimated_delivery_at: string | null
}
export interface RouteIncident {
  id: string; kind: 'bloqueo' | 'accidente'; reason: string; reported_by: string; reported_at: string
  progress_percent: number; position: Location | null; status: 'abierto' | 'resuelto'
  resolved_by: string | null; resolved_at: string | null; decision: 'alternativa' | 'continuar' | 'reprogramado' | null
  resolution_note: string; delay_minutes: number; route_before: (Location | null)[]; alternative: Location[] | null
}
export interface RouteAlternative { revision: number; incident_id: string; points: Location[] }
export interface Trip {
  id: string; revision: number; truck_id: string; truck_name: string; driver_id: string; driver_name: string
  capacity: number; load_units: number; order_codes: string[]; stops: TripStop[]; status: TripStatus
  created_at: string; planned_departure_at: string; actual_departure_at: string | null; progress_percent: number
  closed_at: string | null; completed_order_codes: string[]
  history: { action: string; actor_name: string; at: string; progress_percent: number }[]
  depot: Location; position: Location | null; route_complete: boolean
  incidents: RouteIncident[]; active_incident_id: string | null; excluded_order_codes: string[]
  route_points: (Location | null)[]; route_start_percent: number
}
export interface DispatchSnapshot {
  revision: number; drivers: (DemoActor & { available: boolean })[]; dispatchable_trucks: Truck[]; trips: Trip[]
}
export interface CustomerTracking {
  code: string; status: TripStatus | 'sin_viaje' | 'pendiente_aceptacion' | 'confirmado' | 'entregado'; revision: number; truck_name: string | null; driver_name: string | null
  delivered_at: string | null
  delivery_mode: 'flota_propia' | 'tercero' | null; partner_name: string | null; service_reference: string | null
  actual_departure_at: string | null; progress_percent: number; position: Location | null
  depot: Location; destination: Location | null; route_complete: boolean
  incident_message: string | null; estimated_delivery_at: string | null; needs_reschedule: boolean
}

export const demoApi = {
  deliverOrder: (actor: string, trip: Trip, stop: TripStop, note: string) => request<Trip>(`/api/v1/demo/driver/trips/${encodeURIComponent(trip.id)}/orders/${encodeURIComponent(stop.code)}/deliver`, {
    method: 'POST', headers: { 'X-Demo-Actor': actor }, body: JSON.stringify({ expected_revision: trip.revision, expected_order_revision: stop.order_revision, note }),
  }),
  driverClosedTrips: (actor: string) => request<Trip[]>('/api/v1/demo/driver/trips', { headers: { 'X-Demo-Actor': actor } }),
  thirdParty: (actor: string) => request<ThirdPartySnapshot>('/api/v1/demo/company/third-party', { headers: { 'X-Demo-Actor': actor } }),
  requestThirdParty: (actor: string, order: Order, partnerId: string, reason: string) => request<Order>(`/api/v1/demo/company/orders/${encodeURIComponent(order.code)}/third-party/request`, {
    method: 'POST', headers: { 'X-Demo-Actor': actor }, body: JSON.stringify({ expected_revision: order.revision, partner_id: partnerId, reason }),
  }),
  thirdPartyAct: (actor: string, order: Order, action: ThirdPartyAction, note = '') => request<Order>(`/api/v1/demo/company/orders/${encodeURIComponent(order.code)}/third-party/actions`, {
    method: 'POST', headers: { 'X-Demo-Actor': actor }, body: JSON.stringify({ expected_revision: order.revision, action, note }),
  }),
  context: async () => { const value = await request<DemoContext>('/api/v1/demo/context'); pitchGeneration = value.scenario_generation; return value },
  list: (actor: string) => request<Order[]>('/api/v1/demo/orders', {
    headers: { 'X-Demo-Actor': actor },
  }),
  get: (actor: string, code: string) => request<Order>(`/api/v1/demo/orders/${encodeURIComponent(code)}`, {
    headers: { 'X-Demo-Actor': actor },
  }),
  create: (actor: string, data: OrderInput, key: string) => request<Order>('/api/v1/demo/orders', {
    method: 'POST', headers: { 'X-Demo-Actor': actor, 'Idempotency-Key': key }, body: JSON.stringify(data),
  }),
  correct: (actor: string, code: string, data: OrderInput, revision: number) => request<Order>(`/api/v1/demo/orders/${encodeURIComponent(code)}/correction`, {
    method: 'POST', headers: { 'X-Demo-Actor': actor }, body: JSON.stringify({ order: data, expected_revision: revision }),
  }),
  companyList: (actor: string) => request<Order[]>('/api/v1/demo/company/orders', { headers: { 'X-Demo-Actor': actor } }),
  companyGet: (actor: string, code: string) => request<Order>(`/api/v1/demo/company/orders/${encodeURIComponent(code)}`, { headers: { 'X-Demo-Actor': actor } }),
  companyAct: (actor: string, order: Order, action: CompanyAction, note = '') => request<Order>(`/api/v1/demo/company/orders/${encodeURIComponent(order.code)}/actions`, {
    method: 'POST', headers: { 'X-Demo-Actor': actor }, body: JSON.stringify({ action, note, expected_revision: order.revision }),
  }),
  schedule: (actor: string, order: Order, departure: string, delivery: string | null) => request<Order>(`/api/v1/demo/company/orders/${encodeURIComponent(order.code)}/schedule`, {
    method: 'POST', headers: { 'X-Demo-Actor': actor }, body: JSON.stringify({
      expected_revision: order.revision, scheduled_departure_at: departure, estimated_delivery_at: delivery,
    }),
  }),
  planning: (actor: string) => request<FleetSnapshot>('/api/v1/demo/company/planning', { headers: { 'X-Demo-Actor': actor } }),
  suggest: (actor: string, truckId: string, revision: number, departureDate: string) => request<FleetSuggestion>(`/api/v1/demo/company/trucks/${encodeURIComponent(truckId)}/suggestion`, {
    method: 'POST', headers: { 'X-Demo-Actor': actor }, body: JSON.stringify({ expected_revision: revision, departure_date: departureDate }),
  }),
  assign: (actor: string, truckId: string, revision: number, departureDate: string | null, codes: string[]) => request<FleetSnapshot>(`/api/v1/demo/company/trucks/${encodeURIComponent(truckId)}/assignment`, {
    method: 'POST', headers: { 'X-Demo-Actor': actor }, body: JSON.stringify({ expected_revision: revision, departure_date: departureDate, order_codes: codes }),
  }),
  trips: (actor: string) => request<DispatchSnapshot>('/api/v1/demo/company/trips', { headers: { 'X-Demo-Actor': actor } }),
  createTrip: (actor: string, revision: number, truckId: string, driverId: string) => request<Trip>('/api/v1/demo/company/trips', {
    method: 'POST', headers: { 'X-Demo-Actor': actor }, body: JSON.stringify({ expected_revision: revision, truck_id: truckId, driver_id: driverId }),
  }),
  cancelTrip: (actor: string, trip: Trip) => request<Trip>(`/api/v1/demo/company/trips/${encodeURIComponent(trip.id)}/cancel`, {
    method: 'POST', headers: { 'X-Demo-Actor': actor }, body: JSON.stringify({ expected_revision: trip.revision }),
  }),
  driverTrip: (actor: string) => request<Trip | null>('/api/v1/demo/driver/trip', { headers: { 'X-Demo-Actor': actor } }),
  driverAct: (actor: string, trip: Trip, action: DriverAction) => request<Trip>(`/api/v1/demo/driver/trips/${encodeURIComponent(trip.id)}/actions`, {
    method: 'POST', headers: { 'X-Demo-Actor': actor }, body: JSON.stringify({ expected_revision: trip.revision, action }),
  }),
  tracking: (actor: string, code: string) => request<CustomerTracking>(`/api/v1/demo/orders/${encodeURIComponent(code)}/tracking`, { headers: { 'X-Demo-Actor': actor } }),
  reportIncident: (actor: DemoActor, trip: Trip, kind: 'bloqueo' | 'accidente', reason: string) => request<Trip>(`/api/v1/demo/${actor.role === 'empresa' ? 'company' : 'driver'}/trips/${encodeURIComponent(trip.id)}/incidents`, {
    method: 'POST', headers: { 'X-Demo-Actor': actor.id }, body: JSON.stringify({ expected_revision: trip.revision, kind, reason }),
  }),
  alternative: (actor: string, trip: Trip, incidentId: string) => request<RouteAlternative>(`/api/v1/demo/company/trips/${encodeURIComponent(trip.id)}/incidents/${encodeURIComponent(incidentId)}/alternative`, {
    method: 'POST', headers: { 'X-Demo-Actor': actor }, body: JSON.stringify({ expected_revision: trip.revision }),
  }),
  resolveIncident: (actor: string, trip: Trip, incidentId: string, decision: 'alternativa' | 'continuar', delay: number, note: string) => request<Trip>(`/api/v1/demo/company/trips/${encodeURIComponent(trip.id)}/incidents/${encodeURIComponent(incidentId)}/resolve`, {
    method: 'POST', headers: { 'X-Demo-Actor': actor }, body: JSON.stringify({ expected_revision: trip.revision, decision, delay_minutes: delay, resolution_note: note }),
  }),
  reportProblem: (actor: string, trip: Trip, stop: TripStop, reason: string) => request<Trip>(`/api/v1/demo/driver/trips/${encodeURIComponent(trip.id)}/orders/${encodeURIComponent(stop.code)}/problem`, {
    method: 'POST', headers: { 'X-Demo-Actor': actor }, body: JSON.stringify({ expected_revision: trip.revision, expected_order_revision: stop.order_revision, reason }),
  }),
  reschedule: (actor: string, trip: Trip, stop: TripStop, departure: string, delivery: string | null, note: string) => request<Order>(`/api/v1/demo/company/orders/${encodeURIComponent(stop.code)}/reschedule`, {
    method: 'POST', headers: { 'X-Demo-Actor': actor }, body: JSON.stringify({ expected_revision: stop.order_revision, expected_trip_revision: trip.revision, scheduled_departure_at: departure, estimated_delivery_at: delivery, resolution_note: note }),
  }),
}

export const pitchApi = {
  login: async () => {
    const result = await request<{ access_token: string; expires_at: string }>('/api/v1/pitch/login', { method: 'POST' })
    pitchToken = result.access_token
    return demoApi.context()
  },
  logout: async () => {
    try { await request<void>('/api/v1/pitch/logout', { method: 'POST' }) }
    finally { pitchToken = null; pitchGeneration = null }
  },
  reset: (resetKey: string, generation: string) => request<{ scenario_generation: string }>('/api/v1/pitch/reset', {
    method: 'POST', body: JSON.stringify({ reset_key: resetKey, expected_generation: generation, confirmation: 'REINICIAR' }),
  }),
}
