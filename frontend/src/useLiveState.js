import { useEffect, useRef, useState } from 'react'

/**
 * Subscribe to server-pushed state.
 *
 * The server owns the demo, so the browser is a view onto it: no polling, no local
 * copy of the pipeline, and closing the tab does not stop anything. Reconnects on its
 * own, because a demo machine's network is not always kind.
 */
export function useLiveState() {
  const [state, setState] = useState(null)
  const [connected, setConnected] = useState(false)
  const socket = useRef(null)
  const retry = useRef(null)

  useEffect(() => {
    let closed = false

    const connect = () => {
      const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${protocol}://${location.host}/ws`)
      socket.current = ws

      ws.onopen = () => setConnected(true)
      ws.onmessage = (event) => {
        const message = JSON.parse(event.data)
        if (message.type === 'state') setState(message.payload)
      }
      ws.onclose = () => {
        setConnected(false)
        if (!closed) retry.current = setTimeout(connect, 1500)
      }
      ws.onerror = () => ws.close()
    }

    connect()
    return () => {
      closed = true
      clearTimeout(retry.current)
      socket.current?.close()
    }
  }, [])

  return { state, connected }
}
