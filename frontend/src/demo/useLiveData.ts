import { useEffect, useRef, useState } from 'react'

/** Lecturas de la demo con limpieza al cambiar de actor e invalidación tras una acción. */
export function useLiveData<T>(identity: string, load: () => Promise<T>) {
  const [data, setData] = useState<T>()
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const loader = useRef(load)
  const sequence = useRef(0)
  loader.current = load
  useEffect(() => {
    let active = true
    const read = async () => {
      const ticket = ++sequence.current
      try {
        const value = await loader.current()
        if (active && ticket === sequence.current) { setData(value); setError('') }
      } catch (failure) {
        if (active && ticket === sequence.current) setError(failure instanceof Error ? failure.message : 'No pudimos consultar los datos.')
      }
    }
    void read()
    const timer = window.setInterval(read, 5000)
    return () => { active = false; ++sequence.current; window.clearInterval(timer) }
  }, [identity, attempt])
  return { data, error, refresh: () => setAttempt(value => value + 1), publish: (value: T) => {
    ++sequence.current; setData(value); setError('')
  } }
}
