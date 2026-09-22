import { api } from '@/api/robot'

export interface AuthStatus {
  enabled: boolean
  authenticated: boolean
  username: string
  expires_at: number | null
}

export const authApi = {
  status: () => api.get<AuthStatus>('/auth/status').then((response) => response.data),
  login: (username: string, password: string) =>
    api.post<AuthStatus>('/auth/login', { username, password }).then((response) => response.data),
  logout: () => api.post('/auth/logout'),
}
