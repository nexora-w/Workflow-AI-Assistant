import { WS_URL } from './client';
import type { WSMessage } from '@/types';

export class ChatWebSocket {
  private ws: WebSocket | null = null;
  private chatId: number | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private readonly listeners = new Map<string, Set<(data: WSMessage) => void>>();

  connect(chatId: number) {
    this.disconnect();
    this.chatId = chatId;
    const token =
      typeof window !== 'undefined' ? localStorage.getItem('token') : null;
    if (!token) return;

    const url = `${WS_URL}/ws/${chatId}?token=${encodeURIComponent(token)}`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.startPing();
      this.emit('connected', { type: 'connected', chat_id: chatId } as WSMessage);
    };

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const data: WSMessage = JSON.parse(event.data as string);
        this.emit(data.type, data);
        this.emit('*', data);
      } catch {
        /* ignore malformed */
      }
    };

    this.ws.onclose = (event: CloseEvent) => {
      this.stopPing();
      this.emit('disconnected', { type: 'disconnected', chat_id: chatId } as WSMessage);
      if (event.code !== 4001 && event.code !== 4003 && event.code !== 4004) {
        this.scheduleReconnect(chatId);
      }
    };

    this.ws.onerror = () => {
      /* onclose will run */
    };
  }

  disconnect() {
    this.stopPing();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.chatId = null;
  }

  send(data: object) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  sendTyping(isTyping: boolean) {
    this.send({ type: 'typing', is_typing: isTyping });
  }

  on(event: string, callback: (data: WSMessage) => void) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(callback);
    return () => {
      this.listeners.get(event)?.delete(callback);
    };
  }

  private emit(event: string, data: WSMessage) {
    this.listeners.get(event)?.forEach((cb) => cb(data));
  }

  private startPing() {
    this.pingTimer = setInterval(() => this.send({ type: 'ping' }), 30000);
  }

  private stopPing() {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  private scheduleReconnect(chatId: number) {
    this.reconnectTimer = setTimeout(() => {
      if (this.chatId === null) {
        this.connect(chatId);
      }
    }, 3000);
  }

  get isConnected() {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

export const chatWS = new ChatWebSocket();
