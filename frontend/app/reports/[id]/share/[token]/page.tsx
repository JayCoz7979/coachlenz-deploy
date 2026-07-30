'use client'
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { publicApi } from '@/lib/api'

interface Section { heading?: string; body?: string; insight_type?: string }
interface SharedReport {
  title: string
  sport: string
  report_type: string
  watermarked: boolean
  sections: Section[]
  generated_at: string | null
}

export default function SharedReportPage() {
  const params = useParams<{ id: string; token: string }>()
  const [report, setReport] = useState<SharedReport | null>(null)
  const [error, setError] = useState<{ status?: number; msg: string } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!params.id || !params.token) return
    publicApi
      .get(`/reports/${params.id}/share/${params.token}`)
      .then((r) => setReport(r.data))
      .catch((e) =>
        setError({ status: e.response?.status, msg: e.response?.data?.detail || 'This report is unavailable.' })
      )
      .finally(() => setLoading(false))
  }, [params.id, params.token])

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 share-page">
      <style>{`@media print { .share-page { background:#fff !important; color:#111 !important } .no-print { display:none !important } .share-card { background:#fff !important; border-color:#ddd !important; color:#111 !important } }`}</style>
      <div className="max-w-3xl mx-auto px-4 py-10">
        {loading ? (
          <p className="text-gray-400">Loading…</p>
        ) : error ? (
          <div className="share-card card text-center space-y-2">
            <div className="text-red-400 font-semibold">
              {error.status === 410 ? 'This share link has expired' : 'Report unavailable'}
            </div>
            <p className="text-gray-400 text-sm">{error.msg}</p>
          </div>
        ) : report ? (
          <>
            <div className="flex items-start justify-between mb-6 no-print">
              <div>
                <h1 className="text-2xl font-bold text-brand-400">{report.title}</h1>
                <p className="text-gray-400 text-sm capitalize">{report.sport} · {report.report_type} scouting report</p>
              </div>
              <button onClick={() => window.print()} className="btn-primary">Print / Save PDF</button>
            </div>
            {report.watermarked && (
              <div className="no-print mb-4 text-xs bg-gold/10 border border-gold/30 rounded p-2 text-gold">
                CoachLenz Trial report — upgrade at coachlenz.com to remove this banner.
              </div>
            )}
            <div className="space-y-5">
              {report.sections.map((s, i) => (
                <div key={i} className="share-card card">
                  {s.heading && <h2 className="text-lg font-semibold text-gray-100 mb-2">{s.heading}</h2>}
                  {s.body && <p className="text-gray-300 whitespace-pre-line leading-relaxed">{s.body}</p>}
                </div>
              ))}
              {report.sections.length === 0 && (
                <p className="text-gray-400">This report has no breakdown sections yet.</p>
              )}
            </div>
            {report.generated_at && (
              <p className="text-xs text-gray-600 mt-8">Generated {new Date(report.generated_at).toLocaleDateString()}</p>
            )}
          </>
        ) : null}
        <p className="text-center text-xs text-gray-600 mt-10 no-print">
          Powered by <a href="https://cosbyaisolutions.com" className="text-brand-500 hover:underline" target="_blank" rel="noopener noreferrer">Cosby AI Solutions</a>
        </p>
      </div>
    </div>
  )
}
