'use client'
import { useEffect, useState } from 'react'
import api from '@/lib/api'
import Link from 'next/link'
import OSShell from '@/components/os/OSShell'
import { useAuth } from '@/lib/auth'

export default function ReportsPage() {
  const { user } = useAuth()
  const [reports, setReports] = useState<any[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    if (!user) return
    api.get('/reports').then(r => setReports(r.data || [])).catch(() => {}).finally(() => setLoaded(true))
  }, [user])

  return (
    <OSShell title="Scout Reports">
      <div className="sec-hdr"><div className="sec-title">📋 Scout Reports</div></div>
      <div className="rpt-list">
        {reports.map(r => (
          <Link key={r.id} href={`/reports/${r.id}`} style={{ textDecoration: 'none' }}>
            <div className="rpt-row">
              <div className="rpt-icon">{r.report_type === 'self_scout' ? '🪞' : '📋'}</div>
              <div className="rpt-info">
                <div className="rpt-name">{r.title}</div>
                <div className="rpt-meta" style={{ textTransform: 'capitalize' }}>{r.sport} · {String(r.report_type || 'opponent').replace('_', ' ')}</div>
              </div>
              {r.watermarked && <span className="tag tw">Trial</span>}
              {r.generated_at
                ? <span className="tag tg">Ready</span>
                : <span className="tag tgo">Analyzing…</span>}
            </div>
          </Link>
        ))}
        {loaded && reports.length === 0 && (
          <div className="ai-box" style={{ textAlign: 'center' }}>
            No reports yet. Tag plays on a game film and generate an AI scout report, or{' '}
            <Link href="/scout" style={{ color: 'var(--green3)' }}>start a scout →</Link>
          </div>
        )}
      </div>
      <div className="powered">Powered by <a href="https://cosbyaisolutions.com" target="_blank" rel="noreferrer">Cosby AI Solutions</a></div>
    </OSShell>
  )
}
