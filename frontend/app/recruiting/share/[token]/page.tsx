'use client'
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { publicApi } from '@/lib/api'

interface Highlight { id: string; title: string | null; start_time: number; end_time: number; url: string | null }
interface Profile {
  name: string
  position: string | null
  grade_year: string | null
  highlights: Highlight[]
  stats: { highlights_count: number }
}

export default function SharedRecruitingProfile() {
  const params = useParams<{ token: string }>()
  const [profile, setProfile] = useState<Profile | null>(null)
  const [error, setError] = useState<{ status?: number; msg: string } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!params.token) return
    publicApi
      .get(`/recruiting/share/${params.token}`)
      .then((r) => setProfile(r.data))
      .catch((e) =>
        setError({ status: e.response?.status, msg: e.response?.data?.detail || 'This profile is unavailable.' })
      )
      .finally(() => setLoading(false))
  }, [params.token])

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <div className="max-w-2xl mx-auto px-4 py-10">
        {loading ? (
          <p className="text-gray-400">Loading…</p>
        ) : error ? (
          <div className="card text-center space-y-2">
            <div className="text-red-400 font-semibold">
              {error.status === 410 ? 'This recruiting link has expired' : 'Profile unavailable'}
            </div>
            <p className="text-gray-400 text-sm">{error.msg}</p>
          </div>
        ) : profile ? (
          <>
            <div className="mb-6">
              <div className="text-xs uppercase tracking-wide text-gold font-semibold">Recruiting Profile</div>
              <h1 className="text-3xl font-bold text-brand-400 mt-1">{profile.name}</h1>
              <p className="text-gray-400">
                {[profile.position, profile.grade_year && `Class of ${profile.grade_year}`].filter(Boolean).join(' · ')}
              </p>
            </div>
            <div className="card mb-6">
              <div className="text-sm text-gray-400">Highlights</div>
              <div className="text-2xl font-bold text-gray-100">{profile.stats.highlights_count}</div>
            </div>
            <div className="space-y-3">
              {profile.highlights.map((h) => (
                <div key={h.id} className="card flex items-center justify-between">
                  <div>
                    <div className="text-gray-100 font-medium">{h.title || 'Highlight'}</div>
                    <div className="text-xs text-gray-500">{Math.round(h.end_time - h.start_time)}s clip</div>
                  </div>
                  {h.url && (
                    <a href={h.url} target="_blank" rel="noopener noreferrer" className="btn-primary text-sm">Watch</a>
                  )}
                </div>
              ))}
              {profile.highlights.length === 0 && (
                <p className="text-gray-400">No highlights have been added to this profile yet.</p>
              )}
            </div>
          </>
        ) : null}
        <p className="text-center text-xs text-gray-600 mt-10">
          Powered by <a href="https://cosbyaisolutions.com" className="text-brand-500 hover:underline" target="_blank" rel="noopener noreferrer">Cosby AI Solutions</a>
        </p>
      </div>
    </div>
  )
}
