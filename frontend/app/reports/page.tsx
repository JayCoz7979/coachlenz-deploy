'use client'
import { useEffect, useState } from 'react'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { FileText, Clock, CheckCircle } from 'lucide-react'

export default function ReportsPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const [reports, setReports] = useState<any[]>([])

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])
  useEffect(() => { if (user) api.get('/reports').then(r => setReports(r.data)) }, [user])

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-2xl font-bold mb-6">Reports</h2>
          <div className="space-y-3">
            {reports.map(r => (
              <Link key={r.id} href={`/reports/${r.id}`} style={{ textDecoration: 'none', display: 'block' }}>
                <div className="card flex items-center justify-between" style={{ cursor: 'pointer' }}>
                  <div className="flex items-center gap-3">
                    <FileText size={18} style={{ color: '#C9A84C' }} />
                    <div>
                      <div className="font-semibold">{r.title}</div>
                      <div className="text-sm text-gray-400 mt-1">{r.sport} · {r.report_type}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {r.generated_at
                      ? <span style={{ fontSize: 11, color: '#2d8c40', display: 'flex', alignItems: 'center', gap: 4 }}><CheckCircle size={11} /> Ready</span>
                      : <span style={{ fontSize: 11, color: '#C9A84C', display: 'flex', alignItems: 'center', gap: 4 }}><Clock size={11} /> Processing</span>
                    }
                  </div>
                </div>
              </Link>
            ))}
            {reports.length === 0 && (
              <div className="text-center text-gray-500 py-12">
                No reports yet. Tag plays on a game film and click "Generate AI Report."
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
