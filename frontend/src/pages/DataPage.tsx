import { useState, useEffect, useRef } from 'react'
import {
  fetchShops, queryDataRows, uploadDataFiles,
  updateDataRow, deleteDataRow, createDataRow, exportXlsx
} from '@/api/data'
import { toast } from '@/store/toast'
import type { DataRow } from '@/types'
import Modal from '@/components/Modal'

const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六']
const getWeekday = (d: string) => {
  const day = new Date(d + 'T00:00:00').getDay()
  return `周${WEEKDAYS[day]}`
}
const fmtNum = (n: number | undefined) =>
  n == null ? '-' : Number(n).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const NUM_COLS = [
  { key: 'payment_amount', label: '支付金额', group: '基础数据' },
  { key: 'promotion_cost', label: '全站推广', group: '付费推广' },
  { key: 'marketing_cost', label: '评价有礼+跨店满减', group: '营业费用' },
  { key: 'after_sale_cost', label: '售后费用', group: '营业费用' },
  { key: 'tech_service_fee', label: '技术服务费', group: '营业费用' },
  { key: 'other_cost', label: '其他费用', group: '营业费用' },
  { key: 'platform_refund', label: '平台返还', group: '营业费用' },
] as const

const EMPTY_FORM: Omit<DataRow, 'id'> = {
  shop_name: '', data_date: '',
  payment_amount: 0, promotion_cost: 0, marketing_cost: 0,
  after_sale_cost: 0, tech_service_fee: 0, other_cost: 0, platform_refund: 0,
}

export default function DataPage() {
  const [shops, setShops] = useState<string[]>([])
  const [selShops, setSelShops] = useState<string[]>([])
  const [rows, setRows] = useState<DataRow[]>([])
  const [loading, setLoading] = useState(false)
  const [dragover, setDragover] = useState(false)
  const [uploadMsg, setUploadMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [editing, setEditing] = useState<{ id: number; key: string } | null>(null)
  const [editVal, setEditVal] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [addForm, setAddForm] = useState<Omit<DataRow, 'id'>>({ ...EMPTY_FORM })
  const fileRef = useRef<HTMLInputElement>(null)

  const loadMeta = async () => {
    try {
      const s = await fetchShops()
      setShops(s)
    } catch { /* silent */ }
  }

  const loadRows = async (shops: string[]) => {
    setLoading(true)
    try { setRows(await queryDataRows('', shops)) }
    catch { toast.error('查询失败') }
    finally { setLoading(false) }
  }

  useEffect(() => { loadMeta().then(() => loadRows([])) }, [])

  const toggleShop = (shop: string) => {
    const next = selShops.includes(shop) ? selShops.filter(s => s !== shop) : [...selShops, shop]
    setSelShops(next); loadRows(next)
  }

  const selectAllShops = () => {
    const next = selShops.length === shops.length ? [] : [...shops]
    setSelShops(next); loadRows(next)
  }

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    setUploadMsg(null)
    try {
      const count = await uploadDataFiles(Array.from(files))
      setUploadMsg({ ok: true, text: `成功导入 ${count} 条数据` })
      toast.success(`导入 ${count} 条`)
      await loadMeta()
      loadRows(selShops)
    } catch { setUploadMsg({ ok: false, text: '导入失败' }); toast.error('导入失败') }
  }

  const startEdit = (id: number, key: string, val: number) => {
    setEditing({ id, key }); setEditVal(String(val ?? 0))
  }

  const saveEdit = async (row: DataRow) => {
    if (!editing) return
    const newVal = Number(editVal) || 0
    if (newVal === Number(row[editing.key as keyof DataRow])) { setEditing(null); return }
    try {
      const updated = await updateDataRow(row.id, { [editing.key]: newVal })
      setRows(prev => prev.map(r => r.id === row.id ? updated : r))
      toast.success('已保存')
    } catch { toast.error('保存失败') }
    setEditing(null)
  }

  const handleDelete = async (row: DataRow) => {
    if (!confirm(`确定删除 ${row.shop_name} ${row.data_date} 的数据？`)) return
    try {
      await deleteDataRow(row.id)
      setRows(prev => prev.filter(r => r.id !== row.id))
      toast.success('已删除')
    } catch { toast.error('删除失败') }
  }

  const handleAddSubmit = async () => {
    if (!addForm.shop_name || !addForm.data_date) { toast.error('店铺名和日期必填'); return }
    try {
      await createDataRow(addForm)
      setShowAdd(false); setAddForm({ ...EMPTY_FORM })
      toast.success('已新增')
      await loadMeta()
      loadRows(selShops)
    } catch { toast.error('新增失败') }
  }

  const handleExport = async () => {
    try { await exportXlsx('', selShops); toast.success('导出成功') }
    catch { toast.error('导出失败') }
  }

  // Group by shop
  const grouped = rows.reduce((acc, row) => {
    if (!acc[row.shop_name]) acc[row.shop_name] = []
    acc[row.shop_name].push(row)
    return acc
  }, {} as Record<string, DataRow[]>)

  Object.values(grouped).forEach(arr => arr.sort((a, b) => a.data_date.localeCompare(b.data_date)))

  const getGroupHeaders = () => {
    const groups: { label: string; span: number; cls: string }[] = [
      { label: '', span: 2, cls: '' },
    ]
    let cur = ''
    let span = 0
    for (const col of NUM_COLS) {
      if (col.group === cur) { span++ }
      else { if (cur) groups.push({ label: cur, span, cls: cur === '基础数据' ? 'group-base' : cur === '付费推广' ? 'group-promo' : 'group-cost' }); cur = col.group; span = 1 }
    }
    if (cur) groups.push({ label: cur, span, cls: cur === '基础数据' ? 'group-base' : cur === '付费推广' ? 'group-promo' : 'group-cost' })
    groups.push({ label: '', span: 1, cls: '' })
    return groups
  }

  const totals = (shopRows: DataRow[]) => {
    const t: Record<string, number> = {}
    for (const col of NUM_COLS) t[col.key] = shopRows.reduce((s, r) => s + (Number(r[col.key as keyof DataRow]) || 0), 0)
    return t
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">数据管理与导出</h1>
          <p className="page-subtitle">查询 · 编辑 · 导出店铺日报数据</p>
        </div>
        <div className="flex gap-8">
          <button className="btn btn-sm btn-primary" onClick={() => { setAddForm({ ...EMPTY_FORM, shop_name: selShops.length === 1 ? selShops[0] : '' }); setShowAdd(true) }}>+ 新增数据</button>
          <button className="btn btn-sm btn-success" onClick={handleExport}>导出 XLSX</button>
        </div>
      </div>

      {/* Upload */}
      <div
        className={`upload-zone${dragover ? ' dragover' : ''}`}
        onDragOver={e => { e.preventDefault(); setDragover(true) }}
        onDragLeave={() => setDragover(false)}
        onDrop={e => { e.preventDefault(); setDragover(false); handleUpload(e.dataTransfer.files) }}
        onClick={() => fileRef.current?.click()}
      >
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ margin: '0 auto', color: 'var(--text-3)', display: 'block' }}>
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><polyline points="9 15 12 12 15 15"/>
        </svg>
        <p>点击或拖拽 JSON 文件上传</p>
        <input ref={fileRef} type="file" accept=".json" multiple style={{ display: 'none' }} onChange={e => handleUpload(e.target.files)} />
      </div>
      {uploadMsg && <div className={`upload-result ${uploadMsg.ok ? 'ok' : 'err'}`}>{uploadMsg.text}</div>}

      {/* Filters */}
      <div className="card">
        <div className="flex items-center justify-between mb-16">
          <span className="form-label" style={{ margin: 0 }}>店铺筛选</span>
          <span style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>已选 {selShops.length}/{shops.length} 个店铺</span>
        </div>
        <div className="chip-list">
          <span className={`chip${selShops.length === shops.length && shops.length > 0 ? ' active' : ''}`} onClick={selectAllShops}>全部</span>
          {shops.map(s => (
            <span key={s} className={`chip${selShops.includes(s) ? ' active' : ''}`} onClick={() => toggleShop(s)}>{s}</span>
          ))}
        </div>
      </div>

      {/* Tables */}
      {loading ? (
        <div className="flex items-center gap-8" style={{ padding: 40, justifyContent: 'center', color: 'var(--text-2)' }}>
          <div className="spinner" />加载中...
        </div>
      ) : rows.length === 0 ? (
        <div className="empty-state">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2">
            <rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/>
          </svg>
          <p>暂无数据，请上传 JSON 文件或调整筛选条件</p>
        </div>
      ) : (
        Object.entries(grouped).map(([shop, shopRows]) => (
          <div key={shop} style={{ marginBottom: 24 }}>
            <div className="data-table-wrap">
              <div className="shop-table-header">{shop}</div>
              <div style={{ overflowX: 'auto' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      {getGroupHeaders().map((g, i) => (
                        <th key={i} colSpan={g.span} className={g.cls}>{g.label}</th>
                      ))}
                    </tr>
                    <tr>
                      <th>日期</th>
                      <th>星期</th>
                      {NUM_COLS.map(c => <th key={c.key}>{c.label}</th>)}
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {shopRows.map(row => (
                      <tr key={row.id}>
                        <td style={{ fontWeight: 600 }}>{row.data_date}</td>
                        <td style={{ color: 'var(--text-2)' }}>{getWeekday(row.data_date)}</td>
                        {NUM_COLS.map(col => (
                          <td
                            key={col.key}
                            className="editable"
                            onDoubleClick={() => startEdit(row.id, col.key, Number(row[col.key as keyof DataRow]))}
                          >
                            {editing?.id === row.id && editing.key === col.key ? (
                              <input
                                className="cell-edit"
                                value={editVal}
                                onChange={e => setEditVal(e.target.value)}
                                onBlur={() => saveEdit(row)}
                                onKeyDown={e => { if (e.key === 'Enter') saveEdit(row); else if (e.key === 'Escape') setEditing(null) }}
                                autoFocus
                              />
                            ) : fmtNum(Number(row[col.key as keyof DataRow]))}
                          </td>
                        ))}
                        <td style={{ textAlign: 'center' }}>
                          <button className="btn-icon" onClick={() => handleDelete(row)} title="删除">✕</button>
                        </td>
                      </tr>
                    ))}
                    <tr className="summary-row">
                      <td style={{ fontWeight: 700 }}>合计</td>
                      <td />
                      {NUM_COLS.map(col => <td key={col.key}>{fmtNum(totals(shopRows)[col.key])}</td>)}
                      <td />
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        ))
      )}

      <Modal
        open={showAdd}
        onClose={() => setShowAdd(false)}
        title="新增数据"
        width="min(90vw, 520px)"
        footer={
          <>
            <button className="btn btn-sm" onClick={() => setShowAdd(false)}>取消</button>
            <button className="btn btn-sm btn-primary" onClick={handleAddSubmit}>确认新增</button>
          </>
        }
      >
        <div className="form-grid">
          <label className="form-label">店铺名称</label>
          {shops.length > 0 ? (
            <select className="form-input" value={addForm.shop_name} onChange={e => setAddForm(p => ({ ...p, shop_name: e.target.value }))}>
              <option value="">请选择...</option>
              {shops.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          ) : (
            <input className="form-input" value={addForm.shop_name} onChange={e => setAddForm(p => ({ ...p, shop_name: e.target.value }))} placeholder="店铺名称" />
          )}
          <label className="form-label">日期</label>
          <input type="date" className="form-input" value={addForm.data_date} onChange={e => setAddForm(p => ({ ...p, data_date: e.target.value }))} />
          {NUM_COLS.map(col => (
            <>
              <label key={col.key + 'l'} className="form-label">{col.label}</label>
              <input key={col.key} type="number" className="form-input"
                value={addForm[col.key as keyof Omit<DataRow, 'id' | 'shop_name' | 'data_date' | 'weekday'>]}
                onChange={e => setAddForm(p => ({ ...p, [col.key]: Number(e.target.value) }))} />
            </>
          ))}
        </div>
      </Modal>
    </div>
  )
}
