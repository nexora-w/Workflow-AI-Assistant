import { create } from 'zustand';
import { authApi, User } from './api';

interface AuthState {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  checkAuth: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: null,
  isLoading: true,
  login: async (username: string, password: string) => {
    const data = await authApi.login(username, password);
    localStorage.setItem('token', data.access_token);
    const user = await authApi.getMe();
    set({ user, token: data.access_token });
  },
  register: async (username: string, email: string, password: string) => {
    await authApi.register(username, email, password);
    // Auto-login after registration
    const data = await authApi.login(username, password);
    localStorage.setItem('token', data.access_token);
    const user = await authApi.getMe();
    set({ user, token: data.access_token });
  },
  logout: () => {
    localStorage.removeItem('token');
    set({ user: null, token: null });
  },
  checkAuth: async () => {
    const token = localStorage.getItem('token');
    if (token) {
      try {
        const user = await authApi.getMe();
        set({ user, token, isLoading: false });
      } catch (error) {
        localStorage.removeItem('token');
        set({ user: null, token: null, isLoading: false });
      }
    } else {
      set({ isLoading: false });
    }
  },
}));
