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
  sales_amount: number
  refund_amount: number
  sales_cost: number
  refund_cost: number
  sales_order_count: number
  freight_expense: number
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

export interface JstUploadResult {
  upload_token: string
  filename: string
  total_rows: number
  parsed_rows: number
  parse_errors: { row: number; shop: string; error: string }[]
}

export interface JstPreviewResult {
  preview_id: string
  upload_token: string
  filename: string
  biz_date: string
  stats: {
    total_rows: number
    matched_count: number
    unmatched_count: number
    ambiguous_count: number
    to_insert_count: number
    duplicate_count: number
    parse_error_count: number
  }
  match_details: {
    source_shop_name: string
    matched_shop_name: string | null
    score: number
    is_ambiguous: boolean
    top_candidates: { shop_name: string; score: number }[]
    status: 'matched' | 'unmatched'
  }[]
}

export interface JstCommitResult {
  status: 'committed' | 'already_committed'
  inserted_count: number
  skipped_count: number
  failed_count: number
  log_id: string
}
