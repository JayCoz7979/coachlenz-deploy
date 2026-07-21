'use client'
import { useEffect, useState, useRef } from 'react'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { useRouter, useSearchParams } from 'next/navigation'
import { Suspense } from 'react'

const SPORTS = ['football','flag_football','basketball','baseball','softball','volleyball','soccer']

const SOURCE_LABELS: Record<string, string> = {
  youtube: 'YouTube',
  hudl: 'Hudl',
  nfhs: 'NFHS Network',
  vimeo: 'Vimeo',
  google_drive: 'Google Drive',
  dropbox: 'Dropbox',
  facebook: 'Facebook',
  generic: 'Video URL',
}

function detectSource(url: string): string {
  if (/youtube\.com|youtu\.be/i.test(url)) return 'youtube'
  if (/hudl\.com/i.test(url)) return 'hudl'
  if (/nfhsnetwork\.com/i.test(url)) return 'nfhs'
  if (/vimeo\.com/i.test(url)) return 'vimeo'
  if (/drive\.google\.com/i.test(url)) return 'google_drive'
  if (/dropbox\.com/i.test(url)) return 'dropbox'
  if (/facebook\.com|fb\.watch/i.test(url)) return 'facebook'
  return 'generic'
}

// A Hudl "Download"/bulk-download email link wraps a pre-signed direct MP4 that
// imports WITHOUT any Hudl login. Detect it so we can reassure the coach instead
// of scaring them with the "needs a login" warning meant for watch-page links.
function isHudlDirectDownloadLink(url: string): boolean {
  if (!/hudl\.com/i.test(url)) return false
  try {
    const p = new URL(url)
    const forward = p.searchParams.get('forward') || p.searchParams.get('url') || ''
    const decoded = decodeURIComponent(forward)
    return /vtemp\.hudl\.com|vg\.hudl\.com|\.mp4/i.test(decoded) ||
      /notifications-tracking|bulkdownload|\/download/i.test(url)
  } catch {
    return /notifications-tracking|bulkdownload/i.test(url)
  }
}

type Tab = 'upload' | 'url'

function UploadPageInner() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const searchParams = useSearchParams()
  const [tab, setTab] = useState<Tab>(searchParams.get('tab') === 'url' ? 'url' : 'upload')
  const [teams, setTeams] = useState<any[]>([])
  const [form, setForm] = useState({ title: '', sport: 'football', team_id: '', opponent: '', game_date: '', is_home: '', scout_jersey: '', opponent_jersey: '' })
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm(f => ({ ...f, [k]: e.target.value }))

  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)

  const [videoUrl, setVideoUrl] = useState('')
  const [importing, setImporting] = useState(false)
  const [importJobId, setImportJobId] = useState<string | null>(null)
  const [importStatus, setImportStatus] = useState<string>('')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const [error, setError] = useState('')

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])
  useEffect(() => { if (user) api.get('/teams').then(r => setTeams(r.data)) }, [user])

  useEffect(() => {
    if (!importJobId) return
    pollRef.current = setInterval(async () => {
      try {
        const r = await api.get(`/ingest/job/${importJobId}`)
        const s = r.data.status
        const statusMap: Record<string, string> = {
          queued: 'Queued — waiting for worker...',
          downloading: 'Downloading video...',
          processing: 'Processing & uploading...',
          done: 'Import complete!',
          error: `Failed: ${r.data.error_message || 'Unknown error'}`,
        }
        setImportStatus(statusMap[s] || s)
        if (s === 'done') {
          clearInterval(pollRef.current!)
          setImporting(false)
          setTimeout(() => router.push('/games'), 1500)
        } else if (s === 'error') {
          clearInterval(pollRef.current!)
          setImporting(false)
          setError(r.data.error_message || 'Import failed')
        }
      } catch {}
    }, 3000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [importJobId])

  async function handleFileUpload(e: React.FormEvent) {
    e.preventDefault()
    if (!file) return
    setUploading(true)
    setError('')
    try {
      const gameRes = await api.post('/games', {
        ...form,
        file_name: file.name,
        file_size_bytes: file.size,
        team_id: form.team_id || undefined,
        is_home: form.is_home === '' ? undefined : form.is_home === 'true',
      })
      // Proxy upload through the backend (no browser->R2 PUT, so no R2 CORS needed).
      const fd = new FormData()
      fd.append('file', file)
      await api.post(`/upload/file?game_id=${gameRes.data.id}`, fd, {
        // Let axios set multipart/form-data WITH the boundary — do not set it manually.
        timeout: 0,
        maxContentLength: Infinity,
        maxBodyLength: Infinity,
        onUploadProgress: (ev) => setProgress(Math.round((ev.loaded / (ev.total || 1)) * 100)),
      })
      router.push('/games')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  async function handleUrlImport(e: React.FormEvent) {
    e.preventDefault()
    if (!videoUrl.trim()) return
    setImporting(true)
    setError('')
    setImportStatus('Queuing import...')
    try {
      const res = await api.post('/ingest/url', {
        url: videoUrl.trim(),
        ...form,
        team_id: form.team_id || undefined,
        is_home: form.is_home === '' ? undefined : form.is_home === 'true',
      })
      setImportJobId(res.data.job_id)
      setImportStatus('Queued — waiting for worker...')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Import failed to start')
      setImporting(false)
    }
  }

  const detectedSource = videoUrl ? detectSource(videoUrl) : null
  const hudlDirect = videoUrl ? isHudlDirectDownloadLink(videoUrl) : false

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-2xl mx-auto">
          <div className="flex items-center gap-3 mb-6">
            <button onClick={() => router.back()} className="text-gray-400 hover:text-gray-200 text-sm">← Back</button>
            <h2 className="text-2xl font-bold">Add Game Film</h2>
          </div>

          <div className="flex gap-1 mb-6 bg-gray-800 rounded-lg p-1">
            <button
              onClick={() => { setTab('upload'); setError('') }}
              className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${tab === 'upload' ? 'bg-brand-500 text-white' : 'text-gray-400 hover:text-gray-200'}`}
            >
              Upload File
            </button>
            <button
              onClick={() => { setTab('url'); setError('') }}
              className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${tab === 'url' ? 'bg-brand-500 text-white' : 'text-gray-400 hover:text-gray-200'}`}
            >
              Import from URL
            </button>
          </div>

          <div className="card space-y-4">
            {error && tab === 'url' && hudlDirect && (
              <div className="text-sm bg-yellow-400/10 border border-yellow-400/30 rounded-lg p-3 space-y-1">
                <p className="text-yellow-300 font-medium">That Hudl download link didn't import.</p>
                <p className="text-gray-300">Hudl download links expire quickly. Go back to the email or Hudl, generate a <span className="text-yellow-200">fresh download link</span>, and paste it again right away — no Hudl account needed.</p>
                <p className="text-gray-400">Still stuck? Click the download in Hudl to save the video file, then use the <span className="text-gray-200">Upload File</span> tab.</p>
                <p className="text-xs text-gray-500 mt-1">Details: {error}</p>
              </div>
            )}
            {error && tab === 'url' && !hudlDirect && /hudl|nfhs|capture/i.test(error + ' ' + videoUrl) && (
              <div className="text-sm bg-yellow-400/10 border border-yellow-400/30 rounded-lg p-3 space-y-1">
                <p className="text-yellow-300 font-medium">We couldn't pull that film automatically.</p>
                <p className="text-gray-300">Public/shared links import directly, but this one looks like <span className="text-yellow-200">private or subscription film</span> that requires a login. Your login on your own device doesn't carry over to our server.</p>
                <p className="text-gray-400">Fixes: connect your {/nfhsnetwork/i.test(videoUrl) ? 'NFHS Network' : 'Hudl'} login (contact your CoachLenz admin), or download the film from the source and use the <span className="text-gray-200">Upload File</span> tab — that always works.</p>
                <p className="text-xs text-gray-500 mt-1">Details: {error}</p>
              </div>
            )}
            {error && tab === 'url' && !/hudl|nfhs|capture/i.test(error + ' ' + videoUrl) && (
              <div className="text-sm bg-yellow-400/10 border border-yellow-400/30 rounded-lg p-3 space-y-1">
                <p className="text-yellow-300 font-medium">We couldn't import from that link.</p>
                <p className="text-gray-300">This is almost always the link itself — not CoachLenz. The most common cause is an <span className="text-yellow-200">expired or broken link</span>.</p>
                <p className="text-gray-400">Please go back to the source (e.g. Hudl → Share), copy a <span className="text-gray-200">fresh link</span>, and paste it again.</p>
                <p className="text-xs text-gray-500 mt-1">Details: {error}</p>
              </div>
            )}
            {error && tab !== 'url' && <div className="text-red-400 text-sm bg-red-400/10 rounded p-3">{error}</div>}

            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <label className="label">Game Title</label>
                <input className="input" value={form.title} onChange={set('title')} required placeholder="vs Lincoln High — Week 5" />
              </div>
              <div>
                <label className="label">Sport</label>
                <select className="input" value={form.sport} onChange={set('sport')}>
                  {SPORTS.map(s => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
                </select>
              </div>
              <div>
                <label className="label">Team</label>
                <select className="input" value={form.team_id} onChange={set('team_id')}>
                  <option value="">Select team...</option>
                  {teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </div>
              <div>
                <label className="label">Opponent</label>
                <input className="input" value={form.opponent} onChange={set('opponent')} placeholder="Lincoln High" />
              </div>
              <div>
                <label className="label">Game Date</label>
                <input type="date" className="input" value={form.game_date} onChange={set('game_date')} />
              </div>
              <div>
                <label className="label">Team you want the report on — their jersey</label>
                <input className="input" value={form.scout_jersey} onChange={set('scout_jersey')} placeholder="e.g. green jerseys" />
              </div>
              <div>
                <label className="label">The other team — their jersey</label>
                <input className="input" value={form.opponent_jersey} onChange={set('opponent_jersey')} placeholder="e.g. white jerseys" />
              </div>
            </div>
            <p className="text-xs" style={{ color: '#7a7a6e', marginTop: -4, marginBottom: 8 }}>
              Type each team's jersey color so the AI knows which team to break down. Ten seconds, and your report is about the right team. Strongly recommended.
            </p>

            {tab === 'upload' && (
              <form onSubmit={handleFileUpload} className="space-y-4">
                <div>
                  <label className="label">Game Film (Video File)</label>
                  <input type="file" accept="video/*" className="input" onChange={e => setFile(e.target.files?.[0] || null)} required />
                  <p className="text-xs text-gray-500 mt-1">Max 20GB. MP4, MOV, AVI supported.</p>
                </div>
                {uploading && (
                  <div>
                    <div className="flex justify-between text-sm mb-1"><span>Uploading...</span><span>{progress}%</span></div>
                    <div className="w-full bg-gray-700 rounded-full h-2">
                      <div className="bg-brand-500 h-2 rounded-full transition-all" style={{ width: `${progress}%` }} />
                    </div>
                  </div>
                )}
                <button type="submit" disabled={uploading || !file || !form.title} className="btn-primary w-full">
                  {uploading ? `Uploading ${progress}%...` : 'Upload Film'}
                </button>
              </form>
            )}

            {tab === 'url' && (
              <form onSubmit={handleUrlImport} className="space-y-4">
                <div>
                  <label className="label">Video URL</label>
                  <input
                    className="input"
                    type="url"
                    value={videoUrl}
                    onChange={e => setVideoUrl(e.target.value)}
                    placeholder="Paste YouTube, Hudl, Vimeo, Google Drive, or Dropbox link..."
                    required
                    disabled={importing}
                  />
                  {detectedSource && (
                    <p className="text-xs text-brand-400 mt-1">Detected: {SOURCE_LABELS[detectedSource] || detectedSource}</p>
                  )}
                  {hudlDirect && (
                    <div className="mt-2 text-xs bg-green-500/10 border border-green-500/30 rounded-lg p-2.5 text-gray-300">
                      <span className="text-green-400 font-medium">Hudl download link detected — no Hudl account needed.</span> This link already contains the video file, so we'll import it directly. Hudl download links expire fast, so import now while it's fresh.
                    </div>
                  )}
                  {/hudl\.com/i.test(videoUrl) && !hudlDirect && (
                    <div className="mt-2 text-xs bg-green-500/10 border border-green-500/30 rounded-lg p-2.5 text-gray-300">
                      <span className="text-green-400 font-medium">Hudl link detected.</span> We'll capture and import it automatically. <span className="text-gray-200">No Hudl account?</span> In Hudl, use <span className="text-gray-200">Download</span> on the video and paste the download link it gives you — that imports with no login. For private team film, <a href="/settings/connections" className="text-green-400 underline">connect your Hudl account</a> once and it imports with one click.
                    </div>
                  )}
                  {/nfhsnetwork\.com/i.test(videoUrl) && (
                    <div className="mt-2 text-xs bg-green-500/10 border border-green-500/30 rounded-lg p-2.5 text-gray-300">
                      <span className="text-green-400 font-medium">NFHS Network link detected.</span> We'll capture and import it. NFHS film usually requires a paid subscription/login — free events import directly; for subscription games, your NFHS login must be connected (or download from NFHS and use Upload File).
                    </div>
                  )}
                  <div className="mt-2 flex flex-wrap gap-2">
                    {['YouTube', 'Hudl', 'Vimeo', 'Google Drive', 'Dropbox', 'Facebook'].map(s => (
                      <span key={s} className="text-xs bg-gray-700 text-gray-400 px-2 py-0.5 rounded">{s}</span>
                    ))}
                  </div>

                  {/* Source guidance */}
                  <div className="mt-3 text-xs text-gray-400 bg-gray-800/60 border border-gray-700 rounded-lg p-3 space-y-1.5">
                    <p><span className="text-gray-300 font-medium">Hudl:</span> Paste a Hudl share/watch link and we'll capture and import it automatically. Private team film: download from your Hudl coach account and use Upload File.</p>
                    <p><span className="text-gray-300 font-medium">Vimeo, Google Drive, Dropbox, direct video links:</span> paste the link and we'll import it.</p>
                    <p><span className="text-gray-300 font-medium">Tip:</span> Once imported, the film is copied into your CoachLenz library permanently — it stays yours even if the original link later changes.</p>
                  </div>

                  {/* No-account escape hatch — three ways in without your own Hudl login */}
                  <div className="mt-3 text-xs bg-brand-500/5 border border-brand-500/30 rounded-lg p-3 space-y-1.5">
                    <p className="text-brand-300 font-medium">No Hudl account? Three ways to get your film in:</p>
                    <p><span className="text-gray-200">1. Hudl "Download" link.</span> In Hudl, open the video → <span className="text-gray-200">Download</span>. Hudl emails you a download link — paste that here. It carries the file itself, so it imports with no login.</p>
                    <p><span className="text-gray-200">2. Upload the file.</span> Save the video to your phone or computer, then use the <span className="text-gray-200">Upload File</span> tab. Always works, any source.</p>
                    <p><span className="text-gray-200">3. Free hosts.</span> Put the film on Google Drive, Dropbox, YouTube (unlisted), or Vimeo, set sharing to "anyone with the link," and paste that link — no Hudl required.</p>
                  </div>
                </div>

                {importing && (
                  <div className="bg-brand-500/10 border border-brand-500/30 rounded-lg p-4">
                    <div className="flex items-center gap-3">
                      <div className="w-4 h-4 border-2 border-brand-400 border-t-transparent rounded-full animate-spin" />
                      <span className="text-sm text-brand-300">{importStatus}</span>
                    </div>
                    <p className="text-xs text-gray-500 mt-2">You can leave this page — the import continues in the background.</p>
                  </div>
                )}

                {!importing && importStatus === 'Import complete!' && (
                  <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4 text-green-400 text-sm">
                    Import complete! Redirecting to your games...
                  </div>
                )}

                <button type="submit" disabled={importing || !videoUrl.trim() || !form.title} className="btn-primary w-full">
                  {importing ? 'Importing...' : 'Import Film'}
                </button>
              </form>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}

export default function UploadPage() {
  return (
    <Suspense>
      <UploadPageInner />
    </Suspense>
  )
}
