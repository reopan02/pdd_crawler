export interface Cookie {
  cookie_id: string
  shop_name: string
  status: 'unknown' | 'valid' | 'invalid' | 'validating'
  cookie_count: number
}

export interface Task {
  task_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  has_data: boolean
  created_at: string
}

export interface DataRow {
  id: number
  shop_name: string
  data_date: string
  weekday?: string
  payment_amount: number
  promotion_cost: number
  marketing_cost: number
  after_sale_cost: number
  tech_service_fee: number
  other_cost: number
  platform_refund: number
}

export interface Report {
  [key: string]: unknown
  '店铺名称'?: string
  '数据日期'?: string
}

export type ToastType = 'success' | 'error' | 'info'

export interface ToastItem {
  id: number
  message: string
  type: ToastType
}
