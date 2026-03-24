import { apiClient } from './client'
import type { DataRow } from '@/types'
import { useSessionStore } from '@/store/session'

export const fetchShops = async (): Promise<string[]> => {
  const res = await apiClient.get('/api/data/shops')
  return res.data.shops ?? []
}

export const fetchMonths = async (): Promise<string[]> => {
  const res = await apiClient.get('/api/data/months')
  return res.data.months ?? []
}

export const queryDataRows = async (
  month: string,
  shops: string[],
): Promise<DataRow[]> => {
  const params = new URLSearchParams()
  params.set('month', month)
  if (shops.length > 0) params.set('shops', shops.join(','))
  const res = await apiClient.get(`/api/data/query?${params}`)
  return res.data.rows ?? []
}

export const uploadDataFiles = async (files: File[]): Promise<number> => {
  const fd = new FormData()
  files.forEach((f) => fd.append('files', f))
  const res = await apiClient.post('/api/data/upload', fd)
  return res.data.count ?? 0
}

export const updateDataRow = async (
  id: number,
  fields: Partial<DataRow>,
): Promise<DataRow> => {
  const res = await apiClient.put(`/api/data/rows/${id}`, fields)
  return res.data.row
}

export const deleteDataRow = async (id: number): Promise<void> => {
  await apiClient.delete(`/api/data/rows/${id}`)
}

export const createDataRow = async (row: Omit<DataRow, 'id'>): Promise<void> => {
  await apiClient.post('/api/data/rows', row)
}

export const exportXlsx = async (month: string, shops: string[]): Promise<void> => {
  const { sessionId } = useSessionStore.getState()
  const params = new URLSearchParams()
  params.set('month', month)
  if (shops.length > 0) params.set('shops', shops.join(','))
  const res = await fetch(`/api/data/export?${params}`, {
    headers: { 'X-Session-ID': sessionId },
  })
  if (!res.ok) throw new Error('导出失败')
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `店铺数据_${month}.xlsx`
  a.click()
  URL.revokeObjectURL(url)
}
