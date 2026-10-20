import { useEffect, useRef, useState } from 'react'

export function useDemoAction() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const inFlight = useRef(false)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  return { busy, error, message, perform: async (operation: () => Promise<void>, success: string) => {
    if (inFlight.current) return
    inFlight.current = true; setBusy(true); setError(''); setMessage('')
    try { await operation(); if (mounted.current) setMessage(success) }
    catch (failure) { if (mounted.current) setError(failure instanceof Error ? failure.message : 'No pudimos guardar la acción.') }
    finally { inFlight.current = false; if (mounted.current) setBusy(false) }
  }, isMounted: () => mounted.current }
}
