import { useState, useEffect, useRef } from 'react'
import { fetchCookies, uploadCookieFile, validateCookie, renameCookie, deleteCookie, startQrLogin } from '@/api/cookies'
import { useSessionStore } from '@/store/session'
import { toast } from '@/store/toast'
import type { Cookie } from '@/types'
import Modal from '@/components/Modal'

const STATUS_LABEL: Record<string, string> = {
  unknown: '未知', valid: '有效', invalid: '失效', validating: '验证中'
}

export default function CookiePage() {
  const { sessionId } = useSessionStore()
  const [cookies, setCookies] = useState<Cookie[]>([])
  const [loading, setLoading] = useState(true)
  const [qrModal, setQrModal] = useState({ open: false, qrCode: null as string | null, status: '初始化...' })
  const [previewImg, setPreviewImg] = useState<string | null>(null)
  const [validating, setValidating] = useState<Set<string>>(new Set())
  const esRef = useRef<EventSource | null>(null)

  const load = async () => {
    setLoading(true)
    try { setCookies(await fetchCookies()) } catch { toast.error('加载失败') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try { await uploadCookieFile(file); toast.success('上传成功'); load() } catch (err: unknown) { toast.error(err instanceof Error ? err.message : '上传失败') }
    e.target.value = ''
  }

  const handleValidate = async (id: string) => {
    setValidating(prev => new Set([...prev, id]))
    try { await validateCookie(id); toast.success('验证任务已启动'); load() } catch { toast.error('验证失败') }
    finally { setValidating(prev => { const s = new Set(prev); s.delete(id); return s }) }
  }

  const handleRename = async (c: Cookie) => {
    const name = prompt('输入新店铺名称:', c.shop_name)
    if (!name || name === c.shop_name) return
    try { await renameCookie(c.cookie_id, name); toast.success('已更新'); load() } catch { toast.error('重命名失败') }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('确定删除此 Cookie？')) return
    try { await deleteCookie(id); toast.success('已删除'); load() } catch { toast.error('删除失败') }
  }

  const handleQrLogin = async () => {
    try {
      const taskId = await startQrLogin()
      setQrModal({ open: true, qrCode: null, status: '正在生成二维码...' })
      const es = new EventSource(`/api/qr-login/${taskId}/stream?session_id=${sessionId}`)
      esRef.current = es
      es.addEventListener('qr_code', (e) => {
        const d = JSON.parse(e.data)
        const src = d.image
          ? (d.image.startsWith('data:') ? d.image : `data:image/png;base64,${d.image}`)
          : null
        setQrModal(prev => ({ ...prev, qrCode: src, status: d.message || '请扫码' }))
      })
      es.addEventListener('status', (e) => {
        const d = JSON.parse(e.data)
        setQrModal(prev => ({ ...prev, status: d.message || d.status }))
      })
      es.addEventListener('completed', () => {
        toast.success('扫码登录成功'); closeQr(); load()
      })
      es.addEventListener('error', (e: MessageEvent) => {
        try { const d = JSON.parse(e.data); toast.error(`扫码失败: ${d.error}`) } catch { toast.error('连接中断') }
        es.close()
      })
    } catch { toast.error('启动扫码失败') }
  }

  const closeQr = () => {
    esRef.current?.close(); esRef.current = null
    setQrModal({ open: false, qrCode: null, status: '' })
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Cookie 账号管理</h1>
          <p className="page-subtitle">管理商家登录凭证 · {cookies.length} 个账号</p>
        </div>
        <div className="flex gap-8">
          <label className="btn btn-sm" style={{ cursor: 'pointer' }}>
            上传 JSON
            <input type="file" accept=".json" style={{ display: 'none' }} onChange={handleUpload} />
          </label>
          <button className="btn btn-sm btn-primary" onClick={handleQrLogin}>+ 扫码登录</button>
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>店铺名称</th>
              <th>状态</th>
              <th style={{ textAlign: 'center' }}>Cookie 数量</th>
              <th style={{ textAlign: 'right' }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={4}><div className="flex items-center gap-8" style={{ padding: 24, justifyContent: 'center', color: 'var(--text-2)' }}><div className="spinner" />加载中...</div></td></tr>
            ) : cookies.length === 0 ? (
              <tr><td colSpan={4}>
                <div className="empty-state">
                  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 15v-4H7l5-8v4h4l-5 8z"/>
                  </svg>
                  <p>暂无账号，请扫码登录或上传 Cookie 文件</p>
                </div>
              </td></tr>
            ) : cookies.map((c) => (
              <tr key={c.cookie_id}>
                <td>
                  <span
                    style={{ cursor: 'pointer', borderBottom: '1px dashed var(--border-bright)', fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14 }}
                    onClick={() => handleRename(c)}
                    title="点击重命名"
                  >{c.shop_name || '未命名店铺'}</span>
                </td>
                <td><span className={`badge badge-${c.status}`}>{STATUS_LABEL[c.status] ?? c.status}</span></td>
                <td style={{ textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: 13 }}>{c.cookie_count}</td>
                <td>
                  <div className="flex gap-8 justify-end">
                    <button
                      className="btn btn-sm"
                      onClick={() => handleValidate(c.cookie_id)}
                      disabled={validating.has(c.cookie_id)}
                    >
                      {validating.has(c.cookie_id) ? <><div className="spinner" />验证中</> : '验证'}
                    </button>
                    <button className="btn btn-sm btn-danger" onClick={() => handleDelete(c.cookie_id)}>删除</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* QR Modal */}
      <Modal open={qrModal.open} onClose={closeQr} title="扫码登录">
        <div style={{ textAlign: 'center' }}>
          {qrModal.qrCode ? (
            <img
              src={qrModal.qrCode}
              alt="QR Code"
              style={{ width: 220, height: 220, borderRadius: 12, border: '1px solid var(--border-bright)', cursor: 'zoom-in', objectFit: 'contain', background: '#fff', padding: 8 }}
              onClick={() => setPreviewImg(qrModal.qrCode)}
            />
          ) : (
            <div style={{ width: 220, height: 220, borderRadius: 12, border: '1px dashed var(--border-bright)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto', color: 'var(--text-3)' }}>
              <div className="spinner" style={{ width: 32, height: 32 }} />
            </div>
          )}
          <p style={{ marginTop: 16, fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-2)' }}>{qrModal.status}</p>
        </div>
        <div className="modal-footer">
          <button className="btn btn-sm" onClick={closeQr}>关闭</button>
        </div>
      </Modal>

      {/* Preview overlay */}
      {previewImg && (
        <div
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(8px)', zIndex: 500, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'zoom-out' }}
          onClick={() => setPreviewImg(null)}
        >
          <img src={previewImg} alt="preview" style={{ maxWidth: '90vw', maxHeight: '90vh', borderRadius: 8 }} />
        </div>
      )}
    </div>
  )
}
