import { apiClient } from './client'
import type { Task } from '@/types'

export const startCrawl = async (
  cookieIds: string[],
  operations: string[],
): Promise<string> => {
  const res = await apiClient.post('/api/crawl/start', {
    cookie_ids: cookieIds,
    operations,
  })
  return res.data.task_id
}

export const fetchTasks = async (): Promise<Task[]> => {
  const res = await apiClient.get('/api/tasks')
  return res.data.tasks ?? []
}

export const cleanFromTask = async (taskId: string): Promise<unknown> => {
  const res = await apiClient.post(`/api/clean/from-task/${taskId}`)
  return res.data
}
