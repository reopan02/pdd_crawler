import { apiClient } from './client'
import type { Cookie } from '@/types'

export const fetchCookies = async (): Promise<Cookie[]> => {
  const res = await apiClient.get('/api/cookies')
  return res.data.cookies ?? []
}

export const uploadCookieFile = async (file: File): Promise<void> => {
  const fd = new FormData()
  fd.append('file', file)
  await apiClient.post('/api/cookies/upload', fd)
}

export const validateCookie = async (id: string): Promise<void> => {
  await apiClient.post(`/api/cookies/${id}/validate`)
}

export const renameCookie = async (id: string, shopName: string): Promise<void> => {
  await apiClient.post(`/api/cookies/${id}/rename`, { shop_name: shopName })
}

export const deleteCookie = async (id: string): Promise<void> => {
  await apiClient.delete(`/api/cookies/${id}`)
}

export const startQrLogin = async (): Promise<string> => {
  const res = await apiClient.post('/api/qr-login/start')
  return res.data.task_id
}
