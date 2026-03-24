import { useState, useEffect } from 'react'
import { fetchCookies } from '@/api/cookies'
import { startCrawl, fetchTasks, cleanFromTask } from '@/api/crawl'
import { apiClient } from '@/api/client'
import { useSessionStore } from '@/store/session'
import { toast } from '@/store/toast'
import type { Cookie, Task } from '@/types'

interface ReportRow {
  shop_name: string
  data_date: string
  payment_amount: number
  promotion_cost: number
  marketing_cost: number
  after_sale_cost: number
  tech_service_fee: number
  other_cost: number
  platform_refund: number
  [key: string]: string | number
}

const REPORT_COLS: { key: string; label: string; src: string }[] = [
  { key: 'payment_amount',   label: '成交金额',      src: '成交金额' },
  { key: 'promotion_cost',   label: '全站推广',      src: '全站推广' },
  { key: 'marketing_cost',   label: '评价有礼+跨店', src: '评价有礼+跨店满返（营销账户导出）' },
  { key: 'after_sale_cost',  label: '售后费用',      src: '售后费用（扣款中售后+其他中售后）' },
  { key: 'tech_service_fee', label: '技术服务费',    src: '技术服务费（支出+返还净额）' },
  { key: 'other_cost',       label: '其他费用',      src: '其他费用（排除技术服务费和售后后的剩余）' },
  { key: 'platform_refund',  label: '平台返还',      src: '平台返还（维权）' },
]

const fmtNum = (n: number) =>
  Number(n).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export default function CrawlPage() {
  const { sessionId } = useSessionStore()
  const [cookies, setCookies] = useState<Cookie[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [ops, setOps] = useState({ scrape_home: true, export_bills: true })
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState(0)
  const [message, setMessage] = useState('')
  const [previewRows, setPreviewRows] = useState<ReportRow[]>([])
  const [editing, setEditing] = useState<{ row: number; key: string } | null>(null)
  const [editVal, setEditVal] = useState('')
  const [importing, setImporting] = useState(false)

  const load = async () => {
    try {
      const [cs, ts] = await Promise.all([fetchCookies(), fetchTasks()])
      setCookies(cs.filter(c => c.status !== 'invalid'))
      setTasks(ts)
    } catch { toast.error('加载失败') }
  }

  useEffect(() => { load() }, [])

  const toggle = (id: string) =>
    setSelected(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])

  const selectAll = () =>
    setSelected(prev => prev.length === cookies.length ? [] : cookies.map(c => c.cookie_id))

  const toReportRow = (r: Record<string, unknown>): ReportRow => {
    const row: ReportRow = {
      shop_name: String(r['店铺名称'] ?? ''),
      data_date: String(r['数据日期'] ?? ''),
      payment_amount: 0, promotion_cost: 0, marketing_cost: 0,
      after_sale_cost: 0, tech_service_fee: 0, other_cost: 0, platform_refund: 0,
    }
    for (const col of REPORT_COLS) { row[col.key] = Number(r[col.src] ?? 0) }
    return row
  }

  const handleStart = async () => {
    if (selected.length === 0) { toast.error('请至少选择一个账号'); return }
    const opList = [...(ops.scrape_home ? ['scrape_home'] : []), ...(ops.export_bills ? ['export_bills'] : [])]
    if (opList.length === 0) { toast.error('请至少选择一个操作'); return }
    setPreviewRows([])
    try {
      const taskId = await startCrawl(selected, opList)
      setRunning(true); setProgress(0); setMessage('初始化...')
      const es = new EventSource(`/api/tasks/${taskId}/progress?session_id=${sessionId}`)
      es.addEventListener('progress', (e) => {
        const d = JSON.parse((e as MessageEvent).data)
        setProgress(d.progress ?? 0); setMessage(d.message ?? '')
      })
      es.addEventListener('completed', async () => {
        setRunning(false); setProgress(100); setMessage('采集完成')
        es.close()
        try {
          const data = await cleanFromTask(taskId) as { reports?: Record<string,unknown>[] }
          const reports = data.reports ?? []
          setPreviewRows(reports.map(toReportRow))
          toast.success('采集完成，请确认数据后导入')
        } catch { toast.error('数据清洗失败') }
        load()
      })
      es.addEventListener('error', (e: MessageEvent) => {
        try { const d = JSON.parse(e.data); toast.error(`采集失败: ${d.error}`) } catch { toast.error('采集连接中断') }
        setRunning(false); es.close()
      })
    } catch { toast.error('启动采集失败') }
  }

  const startEdit = (rowIdx: number, key: string, val: number) => {
    setEditing({ row: rowIdx, key }); setEditVal(String(val ?? 0))
  }

  const saveEdit = (rowIdx: number) => {
    if (!editing) return
    const newVal = Number(editVal) || 0
    setPreviewRows(prev => prev.map((r, i) => i === rowIdx ? { ...r, [editing.key]: newVal } : r))
    setEditing(null)
  }

  const handleImport = async () => {
    if (previewRows.length === 0) return
    setImporting(true)
    try {
      let count = 0
      for (const row of previewRows) {
        await apiClient.post('/api/data/rows', row)
        count++
      }
      toast.success(`已导入 ${count} 条数据`)
      setPreviewRows([])
    } catch { toast.error('导入失败') }
    finally { setImporting(false) }
  }

  const STATUS_LABEL: Record<string, string> = { pending: '等待', running: '运行中', completed: '完成', failed: '失败' }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">批量数据采集</h1>
          <p className="page-subtitle">多账号并行采集 · 实时进度推送</p>
        </div>
      </div>

      {/* 账号选择表格 */}
      <div className="card">
        <div className="card-title">
          <span>选择采集账号 ({selected.length}/{cookies.length})</span>
          <button className="btn btn-xs" onClick={selectAll}>{selected.length === cookies.length && cookies.length > 0 ? '取消全选' : '全选'}</button>
        </div>
        {cookies.length === 0 ? (
          <div className="empty-state" style={{ padding: '20px 0' }}>
            <p>无可用账号，请先在 Cookie 管理中添加有效账号</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 40 }}></th>
                  <th>店铺名称</th>
                  <th>状态</th>
                  <th style={{ textAlign: 'center' }}>Cookie 数量</th>
                </tr>
              </thead>
              <tbody>
                {cookies.map(c => (
                  <tr key={c.cookie_id} style={{ cursor: 'pointer' }} onClick={() => toggle(c.cookie_id)}>
                    <td style={{ textAlign: 'center' }}>
                      <div style={{ width: 16, height: 16, borderRadius: 4, border: `2px solid ${selected.includes(c.cookie_id) ? 'var(--primary)' : 'var(--border-bright)'}`, background: selected.includes(c.cookie_id) ? 'var(--primary)' : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto', transition: 'all 0.15s' }}>
                        {selected.includes(c.cookie_id) && <span style={{ color: '#fff', fontSize: 10, lineHeight: 1 }}>✓</span>}
                      </div>
                    </td>
                    <td style={{ fontWeight: 600 }}>{c.shop_name || '未命名'}</td>
                    <td><span className={`badge badge-${c.status}`}>{c.status === 'valid' ? '有效' : c.status === 'validating' ? '验证中' : '未验证'}</span></td>
                    <td style={{ textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-2)' }}>{c.cookie_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 采集操作 & 进度 */}
      <div className="card">
        <div className="card-title">采集操作</div>
        <div className="flex gap-24">
          {[{ key: 'scrape_home', label: '抓取首页概览数据' }, { key: 'export_bills', label: '导出详细账单' }].map(o => (
            <label key={o.key} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 14 }}>
              <div style={{ width: 18, height: 18, borderRadius: 4, border: `2px solid ${ops[o.key as keyof typeof ops] ? 'var(--primary)' : 'var(--border-bright)'}`, background: ops[o.key as keyof typeof ops] ? 'var(--primary)' : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, transition: 'all 0.15s' }}
                onClick={() => setOps(prev => ({ ...prev, [o.key]: !prev[o.key as keyof typeof ops] }))}>
                {ops[o.key as keyof typeof ops] && <span style={{ color: '#fff', fontSize: 11 }}>✓</span>}
              </div>
              {o.label}
            </label>
          ))}
        </div>
        <div style={{ marginTop: 20 }}>
          <button className="btn btn-primary" onClick={handleStart} disabled={running}>
            {running ? <><div className="spinner" />采集中...</> : '▶ 开始批量采集'}
          </button>
        </div>
        {(running || progress > 0) && (
          <div style={{ marginTop: 20 }}>
            <div className="flex items-center justify-between mb-8">
              <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-2)' }}>{message}</span>
              <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--primary)' }}>{progress}%</span>
            </div>
            <div className="progress-wrap"><div className="progress-bar" style={{ width: `${progress}%` }} /></div>
          </div>
        )}
      </div>

      {/* 采集结果预览表格 */}
      {previewRows.length > 0 && (
        <div className="card">
          <div className="card-title">
            <span>采集结果预览 · 双击单元格可编辑</span>
            <button className="btn btn-sm btn-primary" onClick={handleImport} disabled={importing}>
              {importing ? <><div className="spinner" />导入中...</> : `✓ 确认导入数据库 (${previewRows.length} 条)`}
            </button>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>店铺名称</th>
                  <th>数据日期</th>
                  {REPORT_COLS.map(c => <th key={c.key} style={{ textAlign: 'right' }}>{c.label}</th>)}
                </tr>
              </thead>
              <tbody>
                {previewRows.map((row, ri) => (
                  <tr key={ri}>
                    <td style={{ fontWeight: 600 }}>{row.shop_name}</td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>{row.data_date}</td>
                    {REPORT_COLS.map(col => (
                      <td key={col.key} style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 13 }}
                        className="editable"
                        onDoubleClick={() => startEdit(ri, col.key, Number(row[col.key]))}>
                        {editing?.row === ri && editing.key === col.key ? (
                          <input className="cell-edit" value={editVal}
                            onChange={e => setEditVal(e.target.value)}
                            onBlur={() => saveEdit(ri)}
                            onKeyDown={e => { if (e.key === 'Enter') saveEdit(ri); else if (e.key === 'Escape') setEditing(null) }}
                            autoFocus />
                        ) : fmtNum(Number(row[col.key]))}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 历史任务 */}
      {tasks.length > 0 && (
        <div className="card">
          <div className="card-title">历史任务</div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>任务 ID</th><th>状态</th><th>创建时间</th></tr></thead>
              <tbody>
                {tasks.slice().reverse().slice(0, 10).map(t => (
                  <tr key={t.task_id}>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-2)' }}>{t.task_id.slice(0, 16)}...</td>
                    <td><span className={`badge badge-${t.status}`}>{STATUS_LABEL[t.status] ?? t.status}</span></td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-2)' }}>{new Date(t.created_at).toLocaleString('zh-CN')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
