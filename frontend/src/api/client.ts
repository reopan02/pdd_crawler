import axios from 'axios'
import { useSessionStore } from '@/store/session'

export const apiClient = axios.create({
  baseURL: '/',
  timeout: 30000,
})

apiClient.interceptors.request.use((config) => {
  const { sessionId } = useSessionStore.getState()
  config.headers['X-Session-ID'] = sessionId
  return config
})

apiClient.interceptors.response.use(
  (res) => res,
  (err) => {
    const message =
      err.response?.data?.detail ??
      err.response?.data?.message ??
      err.message ??
      '请求失败'
    return Promise.reject(new Error(message))
  },
)
