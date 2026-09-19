export type SocketMessage<T> =
  | { type: 'robot_state'; version: number; data: T }
  | { type: 'heartbeat'; version: number }

export class RobotSocket<T> {
  private socket?: WebSocket
  private reconnectTimer?: number
  private manuallyClosed = false

  constructor(
    private onState: (state: T) => void,
    private onConnection: (connected: boolean) => void,
  ) {}

  connect(): void {
    this.manuallyClosed = false
    const configured = import.meta.env.VITE_WS_URL as string | undefined
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = configured || `${protocol}//${window.location.host}/ws/robot`
    this.socket = new WebSocket(url)
    this.socket.onopen = () => this.onConnection(true)
    this.socket.onmessage = (event) => {
      const message = JSON.parse(event.data) as SocketMessage<T>
      if (message.type === 'robot_state') this.onState(message.data)
    }
    this.socket.onclose = () => {
      this.onConnection(false)
      if (!this.manuallyClosed) this.reconnectTimer = window.setTimeout(() => this.connect(), 2000)
    }
    this.socket.onerror = () => this.socket?.close()
  }

  disconnect(): void {
    this.manuallyClosed = true
    if (this.reconnectTimer) window.clearTimeout(this.reconnectTimer)
    this.socket?.close()
  }
}

