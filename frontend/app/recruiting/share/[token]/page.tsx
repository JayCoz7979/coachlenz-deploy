'use client'
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { publicApi } from '@/lib/api'

interface Highlight { id: string; title: string | null; start_time: number; end_time: number; url: string | null }
interface Profile {
  name: string
  position: string | null
  grade_year: string | null
  sport: string | null
  highlights: Highlight[]
  stats: { highlights_count: number; plays: number; primary_plays: number; total_yards: number; games: number }
  top_play_types: { play_type: string; count: number }[]
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
              <div className="text-sm text-gray-400 mb-3">Season stats</div>
              <div className={`grid ${profile.sport === 'basketball' ? 'grid-cols-4' : 'grid-cols-5'} gap-2 text-center`}>
                <div><div className="text-2xl font-bold text-gray-100 tabular-nums">{profile.stats.plays}</div><div className="text-xs text-gray-500">Plays</div></div>
                <div><div className="text-2xl font-bold text-gray-100 tabular-nums">{profile.stats.primary_plays}</div><div className="text-xs text-gray-500">Primary</div></div>
                {profile.sport !== 'basketball' && <div><div className="text-2xl font-bold text-gray-100 tabular-nums">{profile.stats.total_yards}</div><div className="text-xs text-gray-500">Yards</div></div>}
                <div><div className="text-2xl font-bold text-gray-100 tabular-nums">{profile.stats.games}</div><div className="text-xs text-gray-500">Games</div></div>
                <div><div className="text-2xl font-bold text-gray-100 tabular-nums">{profile.stats.highlights_count}</div><div className="text-xs text-gray-500">Highlights</div></div>
              </div>
              {profile.top_play_types.length > 0 && (
                <p className="text-xs text-gray-500 mt-3 text-center">Most involved on: {profile.top_play_types.map((t) => `${t.play_type} (${t.count})`).join(', ')}</p>
              )}
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
