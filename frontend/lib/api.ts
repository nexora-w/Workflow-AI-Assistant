import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const WS_URL = API_URL.replace(/^http/, 'ws');

const api = axios.create({
  baseURL: API_URL,
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export interface User {
  id: number;
  username: string;
  email: string;
  created_at: string;
}

export interface Chat {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: number;
  chat_id: number;
  role: 'user' | 'assistant';
  content: string;
  workflow_data?: string;
  created_at: string;
}

export interface ChatWithMessages extends Chat {
  messages: Message[];
}

export interface Collaborator {
  id: number;
  user_id: number;
  username: string;
  email: string;
  role: string;
  invited_by: number;
  inviter_username: string;
  created_at: string;
}

export interface SharedChat {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  owner_id: number;
  owner_username: string;
  my_role: string;
}

export interface UserSearchResult {
  id: number;
  username: string;
  email: string;
}

export interface OnlineUser {
  user_id: number;
  username: string;
}

export interface WSMessage {
  type: string;
  chat_id: number;
  [key: string]: any;
}

export interface WorkflowOp {
  op_type: 'move_node' | 'add_node' | 'delete_node' | 'update_node' | 'add_edge' | 'delete_edge';
  payload: Record<string, any>;
}

export interface WorkflowOpResult {
  status: 'applied' | 'merged' | 'conflict';
  version: number;
  data: string;
  conflicts: string[];
}

export interface WorkflowStateData {
  chat_id: number;
  version: number;       // current_version pointer
  max_version: number;   // highest snapshot number
  data: string;
  updated_at: string | null;
  updated_by: number | null;
}

export interface VersionEntry {
  version: number;
  description: string | null;
  created_by: number | null;
  created_by_username: string | null;
  created_at: string;
  is_current: boolean;
}

export interface VersionTimeline {
  chat_id: number;
  current_version: number;
  versions: VersionEntry[];
}

export interface RevertResult {
  version: number;
  data: string;
  message: string;
}

export const authApi = {
  register: async (username: string, email: string, password: string) => {
    const response = await api.post('/auth/register', { username, email, password });
    return response.data;
  },
  login: async (username: string, password: string) => {
    const response = await api.post('/auth/login', { username, password });
    return response.data;
  },
  getMe: async () => {
    const response = await api.get<User>('/auth/me');
    return response.data;
  },
};

export const chatApi = {
  getChats: async () => {
    const response = await api.get<Chat[]>('/chats');
    return response.data;
  },
  getSharedChats: async () => {
    const response = await api.get<SharedChat[]>('/chats/shared');
    return response.data;
  },
  createChat: async (title: string) => {
    const response = await api.post<Chat>('/chats', { title });
    return response.data;
  },
  getChat: async (chatId: number) => {
    const response = await api.get<ChatWithMessages>(`/chats/${chatId}`);
    return response.data;
  },
  deleteChat: async (chatId: number) => {
    const response = await api.delete(`/chats/${chatId}`);
    return response.data;
  },
  sendMessage: async (chatId: number, content: string) => {
    const response = await api.post<Message>(`/chats/${chatId}/messages`, { content });
    return response.data;
  },
  updateWorkflowPositions: async (messageId: number, workflowData: string) => {
    const response = await api.patch(`/messages/${messageId}/workflow`, { workflow_data: workflowData });
    return response.data;
  },
  undoWorkflow: async (chatId: number) => {
    const response = await api.post(`/chats/${chatId}/workflows/undo`);
    return response.data;
  },
  getWorkflowHistory: async (chatId: number) => {
    const response = await api.get(`/chats/${chatId}/workflows/history`);
    return response.data;
  },
};

export const workflowApi = {
  getState: async (chatId: number) => {
    const response = await api.get<WorkflowStateData>(`/chats/${chatId}/workflow/state`);
    return response.data;
  },
  applyOperations: async (chatId: number, baseVersion: number, operations: WorkflowOp[]) => {
    const response = await api.post<WorkflowOpResult>(
      `/chats/${chatId}/workflow/operations`,
      { base_version: baseVersion, operations }
    );
    return response.data;
  },
  getVersionTimeline: async (chatId: number) => {
    const response = await api.get<VersionTimeline>(`/chats/${chatId}/workflow/versions`);
    return response.data;
  },
  revertToVersion: async (chatId: number, targetVersion: number) => {
    const response = await api.post<RevertResult>(
      `/chats/${chatId}/workflow/revert`,
      { target_version: targetVersion }
    );
    return response.data;
  },
  getVersionSnapshot: async (chatId: number, version: number) => {
    const response = await api.get(`/chats/${chatId}/workflow/versions/${version}`);
    return response.data;
  },
};

export const collaborationApi = {
  searchUsers: async (query: string) => {
    const response = await api.get<UserSearchResult[]>(`/users/search?q=${encodeURIComponent(query)}`);
    return response.data;
  },
  addCollaborator: async (chatId: number, username: string, role: string = 'editor') => {
    const response = await api.post<Collaborator>(`/chats/${chatId}/collaborators`, { username, role });
    return response.data;
  },
  getCollaborators: async (chatId: number) => {
    const response = await api.get<Collaborator[]>(`/chats/${chatId}/collaborators`);
    return response.data;
  },
  removeCollaborator: async (chatId: number, userId: number) => {
    const response = await api.delete(`/chats/${chatId}/collaborators/${userId}`);
    return response.data;
  },
  updateCollaboratorRole: async (chatId: number, userId: number, role: string) => {
    const response = await api.patch(`/chats/${chatId}/collaborators/${userId}`, { username: '', role });
    return response.data;
  },
  getOnlineUsers: async (chatId: number) => {
    const response = await api.get<{ users: OnlineUser[] }>(`/chats/${chatId}/online`);
    return response.data.users;
  },
};

// WebSocket connection manager for real-time collaboration
export class ChatWebSocket {
  private ws: WebSocket | null = null;
  private chatId: number | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private listeners: Map<string, Set<(data: WSMessage) => void>> = new Map();

  connect(chatId: number) {
    this.disconnect();
    this.chatId = chatId;

    const token = localStorage.getItem('token');
    if (!token) return;

    const url = `${WS_URL}/ws/${chatId}?token=${encodeURIComponent(token)}`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.startPing();
      this.emit('connected', { type: 'connected', chat_id: chatId });
    };

    this.ws.onmessage = (event) => {
      try {
        const data: WSMessage = JSON.parse(event.data);
        this.emit(data.type, data);
        this.emit('*', data);
      } catch {
        // Ignore malformed messages
      }
    };

    this.ws.onclose = (event) => {
      this.stopPing();
      this.emit('disconnected', { type: 'disconnected', chat_id: chatId });
      if (event.code !== 4001 && event.code !== 4003 && event.code !== 4004) {
        this.scheduleReconnect(chatId);
      }
    };

    this.ws.onerror = () => {
      // Will trigger onclose
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
    this.listeners.get(event)?.forEach(cb => cb(data));
  }

  private startPing() {
    this.pingTimer = setInterval(() => {
      this.send({ type: 'ping' });
    }, 30000);
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


// ============================================================
// Streaming types & SSE client for partial workflow updates
// ============================================================

export interface StreamingNode {
  id: string;
  label: string;
  type: string;
}

export interface StreamingEdge {
  from: string;
  to: string;
}

export interface StreamCallbacks {
  onStreamStart?: (data: { user_message_id: number }) => void;
  onTextChunk?: (data: { content: string }) => void;
  onNodeAdd?: (data: { node: StreamingNode }) => void;
  onEdgeAdd?: (data: { edge: StreamingEdge }) => void;
  onWorkflowComplete?: (data: { workflow_data: string | null; display_content: string }) => void;
  onStreamEnd?: (data: { message_id: number; workflow_version: number | null }) => void;
  onError?: (error: string) => void;
}

export const streamApi = {
  /**
   * Send a message and receive the AI response as Server-Sent Events.
   * Returns an AbortController so the caller can cancel mid-stream.
   */
  streamMessage: (chatId: number, content: string, callbacks: StreamCallbacks): AbortController => {
    const token = localStorage.getItem('token');
    const controller = new AbortController();

    (async () => {
      try {
        const response = await fetch(`${API_URL}/chats/${chatId}/messages/stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ content }),
          signal: controller.signal,
        });

        if (!response.ok) {
          let detail = 'Stream request failed';
          try {
            const err = await response.json();
            detail = err.detail || detail;
          } catch { /* ignore parse errors */ }
          callbacks.onError?.(detail);
          return;
        }

        const reader = response.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // SSE events are separated by double newlines
          const parts = buffer.split('\n\n');
          buffer = parts.pop() || '';

          for (const part of parts) {
            if (!part.trim()) continue;

            let eventType = '';
            let eventData = '';

            for (const line of part.split('\n')) {
              if (line.startsWith('event: ')) {
                eventType = line.slice(7);
              } else if (line.startsWith('data: ')) {
                eventData = line.slice(6);
              }
            }

            if (!eventType || !eventData) continue;

            try {
              const data = JSON.parse(eventData);
              switch (eventType) {
                case 'stream_start':
                  callbacks.onStreamStart?.(data);
                  break;
                case 'text_chunk':
                  callbacks.onTextChunk?.(data);
                  break;
                case 'node_add':
                  callbacks.onNodeAdd?.(data);
                  break;
                case 'edge_add':
                  callbacks.onEdgeAdd?.(data);
                  break;
                case 'workflow_complete':
                  callbacks.onWorkflowComplete?.(data);
                  break;
                case 'stream_end':
                  callbacks.onStreamEnd?.(data);
                  break;
                case 'error':
                  callbacks.onError?.(data.error || 'Unknown stream error');
                  break;
              }
            } catch {
              // Ignore malformed SSE data
            }
          }
        }
      } catch (err: any) {
        if (err.name !== 'AbortError') {
          callbacks.onError?.(err.message || 'Stream connection failed');
        }
      }
    })();

    return controller;
  },
};


export default api;
