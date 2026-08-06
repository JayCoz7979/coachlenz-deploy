'use client'
import { AlertTriangle } from 'lucide-react'

/**
 * In-app confirmation dialog. Replaces native window.confirm(), which some browser
 * contexts (embedded/preview panes) silently auto-cancel — making destructive
 * buttons appear to do nothing. This renders in the DOM, so it works everywhere.
 */
export default function ConfirmModal({
  open, title, message, confirmLabel = 'Delete', cancelLabel = 'Cancel',
  danger = true, busy = false, onConfirm, onCancel,
}: {
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
         role="dialog" aria-modal="true" onClick={onCancel}>
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 max-w-md w-full shadow-2xl"
           onClick={e => e.stopPropagation()}>
        <div className="flex items-start gap-3 mb-2">
          {danger && <AlertTriangle className="text-red-400 shrink-0 mt-0.5" size={22} />}
          <h3 className="text-lg font-semibold">{title}</h3>
        </div>
        <p className="text-sm text-gray-400 mb-6 whitespace-pre-line">{message}</p>
        <div className="flex justify-end gap-2">
          <button onClick={onCancel} disabled={busy} className="btn-secondary disabled:opacity-50">{cancelLabel}</button>
          <button onClick={onConfirm} disabled={busy}
                  className={`px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50 ${danger ? 'bg-red-600 hover:bg-red-500 text-white' : 'bg-brand-500 hover:bg-brand-400 text-white'}`}>
            {busy ? 'Working…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
