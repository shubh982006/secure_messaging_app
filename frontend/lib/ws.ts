import { WS_URL, tokens } from "./api";
import type { WsEnvelope } from "./types";

type Listener = (event: WsEnvelope) => void;
type StatusListener = (status: SocketStatus) => void;

export type SocketStatus = "connecting" | "open" | "reconnecting" | "closed";

/**
 * Resilient WebSocket client.
 *
 * The socket is the fast path, never the source of truth: on every reconnect
 * the app refetches from REST, so a dropped connection can lose events without
 * losing messages.
 */
class SignalSocket {
  private socket: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private statusListeners = new Set<StatusListener>();
  private attempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeat: ReturnType<typeof setInterval> | null = null;
  private closedByUs = false;
  private queue: string[] = [];

  status: SocketStatus = "closed";

  connect() {
    if (typeof window === "undefined") return;
    const token = tokens.access;
    if (!token) return;
    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.closedByUs = false;
    this.setStatus(this.attempt === 0 ? "connecting" : "reconnecting");

    const socket = new WebSocket(`${WS_URL}/api/v1/ws?token=${encodeURIComponent(token)}`);
    this.socket = socket;

    socket.onopen = () => {
      this.attempt = 0;
      this.setStatus("open");
      this.queue.splice(0).forEach((message) => socket.send(message));
      this.heartbeat = setInterval(() => {
        this.send("presence.ping", {});
      }, 25000);
    };

    socket.onmessage = (raw) => {
      let event: WsEnvelope;
      try {
        event = JSON.parse(raw.data);
      } catch {
        return;
      }
      this.listeners.forEach((listener) => listener(event));
    };

    socket.onclose = (event) => {
      this.clearHeartbeat();
      this.socket = null;
      if (this.closedByUs) {
        this.setStatus("closed");
        return;
      }
      // 4401 means the token is no longer valid - reconnecting would just loop.
      if (event.code === 4401) {
        this.setStatus("closed");
        this.listeners.forEach((listener) =>
          listener({ type: "auth.expired", id: "", ts: "", payload: {} }),
        );
        return;
      }
      this.scheduleReconnect();
    };

    socket.onerror = () => socket.close();
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) return;
    this.setStatus("reconnecting");
    // Exponential backoff to 20s, with jitter so a restarted server does not
    // get every client back at the same instant.
    const base = Math.min(20000, 500 * 2 ** this.attempt);
    const delay = base * (0.7 + Math.random() * 0.6);
    this.attempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private clearHeartbeat() {
    if (this.heartbeat) {
      clearInterval(this.heartbeat);
      this.heartbeat = null;
    }
  }

  private setStatus(status: SocketStatus) {
    if (this.status === status) return;
    this.status = status;
    this.statusListeners.forEach((listener) => listener(status));
  }

  send(type: string, payload: Record<string, unknown>) {
    const message = JSON.stringify({
      type,
      id: crypto.randomUUID(),
      ts: new Date().toISOString(),
      payload,
    });
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(message);
      return true;
    }
    // Buffer a small backlog so a send during a blip is not silently dropped.
    if (this.queue.length < 50) this.queue.push(message);
    return false;
  }

  on(listener: Listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  onStatus(listener: StatusListener) {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }

  disconnect() {
    this.closedByUs = true;
    this.attempt = 0;
    this.queue = [];
    this.clearHeartbeat();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.socket?.close();
    this.socket = null;
    this.setStatus("closed");
  }
}

export const socket = new SignalSocket();
