import { api } from './client';
import type { Collaborator, UserSearchResult, OnlineUser } from '@/types';

export const collaborationApi = {
  searchUsers: async (query: string) => {
    const response = await api.get<UserSearchResult[]>(
      `/users/search?q=${encodeURIComponent(query)}`
    );
    return response.data;
  },
  addCollaborator: async (chatId: number, username: string, role: string = 'editor') => {
    const response = await api.post<Collaborator>(`/chats/${chatId}/collaborators`, {
      username,
      role,
    });
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
    const response = await api.patch(`/chats/${chatId}/collaborators/${userId}`, {
      username: '',
      role,
    });
    return response.data;
  },
  getOnlineUsers: async (chatId: number) => {
    const response = await api.get<{ users: OnlineUser[] }>(`/chats/${chatId}/online`);
    return response.data.users;
  },
};
