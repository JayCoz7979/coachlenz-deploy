'use client'
import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import Link from 'next/link'
import { ChevronLeft, Loader2, FileText, AlertTriangle, TrendingUp, Shield, Zap, Target } from 'lucide-react'

interface Section {
  heading: string
  body: string
  insight_type?: string
}

interface Report {
  id: string
  title: string
  sport: string
  report_type: string
  is_trial: boolean
  watermarked: boolean
  sections: Section[]
  summary: any
  generated_at: string | null
}

const SECTION_ICONS: Record<string, any> = {
  run: TrendingUp,
  pass: Target,
  defense: Shield,
  red_zone: Zap,
  tendency: TrendingUp,
  default: FileText,
}

function SectionCard({ section }: { section: Section }) {
  const Icon = SECTION_ICONS[section.insight_type ?? 'default'] ?? SECTION_ICONS.default
  return (
    <div style={{
      background: '#2e2e2e', borderRadius: 6, padding: '20px 24px',
      border: '1px solid rgba(255,255,255,0.06)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <div style={{
          width: 32, height: 32, borderRadius: 6,
          background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.2)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon size={15} style={{ color: '#C9A84C' }} />
        </div>
        <h3 style={{ fontSize: 14, fontWeight: 700, color: '#f8f6f0', letterSpacing: '0.04em' }}>
          {section.heading}
        </h3>
      </div>
      <p style={{ fontSize: 13, color: '#ede9df', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
        {section.body}
      </p>
    </div>
  )
}

export default function ReportPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const { user, isLoading, fetchMe } = useAuth()
  const [report, setReport] = useState<Report | null>(null)
  const [polling, setPolling] = useState(false)

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])

  useEffect(() => {
    if (!user || !id) return
    const load = () => api.get(`/reports/${id}`).then(r => {
      setReport(r.data)
      if (!r.data.generated_at) setPolling(true)
      else setPolling(false)
    })
    load()
  }, [user, id])

  // Poll every 5s while still processing
  useEffect(() => {
    if (!polling) return
    const t = setInterval(() => {
      api.get(`/reports/${id}`).then(r => {
        setReport(r.data)
        if (r.data.generated_at) { setPolling(false) }
      })
    }, 5000)
    return () => clearInterval(t)
  }, [polling, id])

  if (!report) {
    return (
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 flex items-center justify-center">
          <Loader2 size={24} style={{ color: '#C9A84C', animation: 'spin 1s linear infinite' }} />
        </main>
      </div>
    )
  }

  const isProcessing = !report.generated_at

  return (
    <div className="flex h-screen overflow-hidden">
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        {/* Header */}
        <div style={{
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          padding: '14px 32px', position: 'sticky', top: 0,
          background: '#1c1c1c', zIndex: 10,
          display: 'flex', alignItems: 'center', gap: 14,
        }}>
          <Link href="/reports" style={{ color: '#7a7a6e', display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, textDecoration: 'none' }}>
            <ChevronLeft size={15} /> Reports
          </Link>
          <span style={{ color: 'rgba(255,255,255,0.15)' }}>/</span>
          <span style={{ fontSize: 14, fontWeight: 600, color: '#f8f6f0' }}>{report.title}</span>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
            {report.watermarked && (
              <span style={{
                fontSize: 10, color: '#C9A84C', letterSpacing: '0.12em',
                background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.2)',
                padding: '3px 10px', borderRadius: 12,
              }}>TRIAL REPORT</span>
            )}
            {report.generated_at && (
              <span style={{ fontSize: 11, color: '#7a7a6e' }}>
                {new Date(report.generated_at).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>

        <div style={{ maxWidth: 860, margin: '0 auto', padding: '32px 32px 64px' }}>
          {/* Processing state */}
          {isProcessing && (
            <div style={{
              background: 'rgba(201,168,76,0.07)', border: '1px solid rgba(201,168,76,0.2)',
              borderRadius: 8, padding: '24px 32px', textAlign: 'center', marginBottom: 32,
            }}>
              <Loader2 size={32} style={{ color: '#C9A84C', animation: 'spin 1s linear infinite', margin: '0 auto 12px', display: 'block' }} />
              <div style={{ fontSize: 15, fontWeight: 600, color: '#f8f6f0', marginBottom: 6 }}>
                AI is analyzing your film...
              </div>
              <div style={{ fontSize: 13, color: '#7a7a6e' }}>
                This usually takes 30–90 seconds. The page will update automatically.
              </div>
            </div>
          )}

          {/* Summary box */}
          {report.summary && (
            <div style={{
              background: 'linear-gradient(135deg, rgba(26,92,42,0.15), rgba(26,92,42,0.05))',
              border: '1px solid rgba(45,140,64,0.25)',
              borderRadius: 8, padding: '20px 24px', marginBottom: 28,
            }}>
              <div style={{ fontSize: 11, letterSpacing: '0.15em', color: '#2d8c40', marginBottom: 8, fontWeight: 700 }}>
                EXECUTIVE SUMMARY
              </div>
              {typeof report.summary === 'string'
                ? <p style={{ fontSize: 14, color: '#ede9df', lineHeight: 1.7 }}>{report.summary}</p>
                : Object.entries(report.summary).map(([k, v]) => (
                  <div key={k} style={{ marginBottom: 8 }}>
                    <span style={{ fontSize: 11, color: '#7a7a6e', textTransform: 'capitalize' }}>{k.replace(/_/g, ' ')}: </span>
                    <span style={{ fontSize: 13, color: '#ede9df' }}>{String(v)}</span>
                  </div>
                ))
              }
            </div>
          )}

          {/* Watermark banner */}
          {report.watermarked && (
            <div style={{
              background: 'rgba(201,168,76,0.05)', border: '1px dashed rgba(201,168,76,0.3)',
              borderRadius: 6, padding: '12px 20px', marginBottom: 24,
              display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, color: '#C9A84C',
            }}>
              <AlertTriangle size={14} />
              This is a trial report. <Link href="/settings/billing" style={{ color: '#C9A84C', fontWeight: 700 }}>Upgrade</Link> to unlock full reports with unlimited plays and export.
            </div>
          )}

          {/* Sections */}
          {report.sections && report.sections.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ fontSize: 11, letterSpacing: '0.15em', color: '#7a7a6e', marginBottom: 4, fontWeight: 700 }}>
                TENDENCY ANALYSIS — {report.sections.length} SECTION{report.sections.length !== 1 ? 'S' : ''}
              </div>
              {report.sections.map((s, i) => <SectionCard key={i} section={s} />)}
            </div>
          ) : !isProcessing ? (
            <div style={{ textAlign: 'center', color: '#7a7a6e', padding: '48px 0' }}>
              <FileText size={40} style={{ margin: '0 auto 12px', display: 'block', opacity: 0.3 }} />
              <div>No report content generated. The AI worker may still be starting up.</div>
            </div>
          ) : null}
        </div>
      </main>
    </div>
  )
}
