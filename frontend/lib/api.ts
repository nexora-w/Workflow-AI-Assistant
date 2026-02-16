import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

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

export default api;
