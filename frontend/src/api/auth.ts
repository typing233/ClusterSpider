import api from './client'

export async function login(username: string, password: string) {
  const res = await api.post('/auth/login', { username, password })
  return res.data
}

export async function register(username: string, email: string, password: string) {
  const res = await api.post('/auth/register', { username, email, password })
  return res.data
}

export async function getMe() {
  const res = await api.get('/users/me')
  return res.data
}
