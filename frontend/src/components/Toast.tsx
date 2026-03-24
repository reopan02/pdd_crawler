import { useToastStore } from '@/store/toast'
import type { ToastType } from '@/types'

const icons: Record<ToastType, string> = {
  success: '✓',
  error: '✕',
  info: 'i',
}

export default function ToastContainer() {
  const { toasts, removeToast } = useToastStore()
  return (
    <div className="toast-container">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast-${t.type}`} onClick={() => removeToast(t.id)}>
          <span style={{
            width: 20, height: 20, borderRadius: '50%', display: 'flex',
            alignItems: 'center', justifyContent: 'center', fontSize: 11,
            fontWeight: 700, flexShrink: 0,
            background: t.type === 'success' ? 'var(--success-dim)' : t.type === 'error' ? 'var(--danger-dim)' : 'var(--primary-dim)',
            color: t.type === 'success' ? 'var(--success)' : t.type === 'error' ? 'var(--danger)' : 'var(--primary)',
          }}>{icons[t.type]}</span>
          <span style={{ flex: 1 }}>{t.message}</span>
        </div>
      ))}
    </div>
  )
}
