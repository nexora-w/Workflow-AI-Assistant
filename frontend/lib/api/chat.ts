import { api } from './client';
import type { Chat, ChatWithMessages, Message, SharedChat } from '@/types';

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
    const response = await api.patch(`/messages/${messageId}/workflow`, {
      workflow_data: workflowData,
    });
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
