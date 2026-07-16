'use client'
import { useEffect, useState } from 'react'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { useRouter } from 'next/navigation'
import { Link2, CheckCircle, Loader2, Trash2, Shield } from 'lucide-react'

interface Connection {
  provider: string
  account_email: string | null
  status: string
  last_error: string | null
  connected_at: string | null
}

export default function ConnectionsPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const [connections, setConnections] = useState<Connection[]>([])
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [cookies, setCookies] = useState('')
  const [mode, setMode] = useState<'cookies' | 'login'>('cookies')
  const [ytCookies, setYtCookies] = useState('')
  const [ytSaving, setYtSaving] = useState(false)
  const [ytMsg, setYtMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])
  useEffect(() => { if (user) load() }, [user])

  const load = () => api.get('/connections').then(r => setConnections(r.data)).catch(() => {})

  const hudl = connections.find(c => c.provider === 'hudl')
  const youtube = connections.find(c => c.provider === 'youtube')

  const handleConnectYoutube = async (e: React.FormEvent) => {
    e.preventDefault()
    setYtSaving(true); setYtMsg(null)
    try {
      await api.post('/connections', { provider: 'youtube', cookies: ytCookies.trim() })
      setYtCookies('')
      setYtMsg({ kind: 'ok', text: 'YouTube connected. YouTube imports now pull HD instead of 360p.' })
      load()
    } catch (err: any) {
      setYtMsg({ kind: 'err', text: err?.response?.data?.detail || 'Could not connect. Check the cookies and try again.' })
    } finally {
      setYtSaving(false)
    }
  }
  const handleDisconnectYoutube = async () => {
    await api.delete('/connections/youtube'); setYtMsg(null); load()
  }

  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true); setMsg(null)
    try {
      const payload = mode === 'cookies'
        ? { provider: 'hudl', cookies: cookies.trim() }
        : { provider: 'hudl', email: email.trim(), password }
      await api.post('/connections', payload)
      setEmail(''); setPassword(''); setCookies('')
      setMsg({ kind: 'ok', text: 'Hudl connected. Private film now imports in HD — jersey numbers become readable.' })
      load()
    } catch (err: any) {
      setMsg({ kind: 'err', text: err?.response?.data?.detail || 'Could not connect. Check your details and try again.' })
    } finally {
      setSaving(false)
    }
  }

  const handleDisconnect = async () => {
    await api.delete('/connections/hudl')
    setMsg(null)
    load()
  }

  if (isLoading || !user) return null

  return (
    <div className="flex h-screen overflow-hidden">
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-2xl mx-auto">
          <h2 className="text-2xl font-bold mb-1">Connected Accounts</h2>
          <p className="text-gray-400 text-sm mb-6">Connect a film source once, then import private film with one click — no links, no downloads.</p>

          {/* Hudl card */}
          <div className="card">
            <div className="flex items-center gap-3 mb-4">
              <div style={{ width: 38, height: 38, borderRadius: 8, background: 'rgba(45,140,64,0.12)', border: '1px solid rgba(45,140,64,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Link2 size={18} style={{ color: '#2d8c40' }} />
              </div>
              <div>
                <div className="font-semibold">Hudl</div>
                <div className="text-xs text-gray-400">Import private team film directly from your Hudl account</div>
              </div>
              {hudl && (
                <span style={{ marginLeft: 'auto', fontSize: 11, color: '#2d8c40', display: 'flex', alignItems: 'center', gap: 5 }}>
                  <CheckCircle size={12} /> Connected
                </span>
              )}
            </div>

            {hudl ? (
              <div>
                <div className="text-sm text-gray-300 mb-3">
                  Connected as <span className="text-gray-100">{hudl.account_email}</span>
                  {hudl.status === 'error' && hudl.last_error && (
                    <div className="text-xs text-red-400 mt-1">Last import issue: {hudl.last_error}</div>
                  )}
                </div>
                <button onClick={handleDisconnect} className="btn-secondary flex items-center gap-2 text-sm">
                  <Trash2 size={14} /> Disconnect
                </button>
              </div>
            ) : (
              <form onSubmit={handleConnect} className="space-y-3">
                <div style={{ display: 'flex', gap: 6, marginBottom: 4 }}>
                  <button type="button" onClick={() => setMode('cookies')} className={mode === 'cookies' ? 'btn-primary' : 'btn-secondary'} style={{ flex: 1, fontSize: 12 }}>Paste cookies (HD)</button>
                  <button type="button" onClick={() => setMode('login')} className={mode === 'login' ? 'btn-primary' : 'btn-secondary'} style={{ flex: 1, fontSize: 12 }}>Email &amp; password</button>
                </div>
                {mode === 'cookies' ? (
                  <div>
                    <label className="label">Hudl cookies (Netscape format)</label>
                    <textarea className="input" style={{ minHeight: 120, fontFamily: 'monospace', fontSize: 11 }}
                      value={cookies} onChange={e => setCookies(e.target.value)}
                      placeholder={'# Netscape HTTP Cookie File\n.hudl.com\tTRUE\t/\tTRUE\t...\tsession\t...'} />
                    <div className="text-xs text-gray-500 mt-1">
                      Log into Hudl in your browser, export cookies with a "cookies.txt" extension, and paste here. Most reliable path and required to pull HD private film.
                    </div>
                  </div>
                ) : (
                  <>
                    <div>
                      <label className="label">Hudl email</label>
                      <input className="input" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="coach@school.org" />
                    </div>
                    <div>
                      <label className="label">Hudl password</label>
                      <input className="input" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" />
                    </div>
                    <div className="text-xs text-gray-500">Automated login can fail if Hudl requires two-factor. If it does, use "Paste cookies" instead.</div>
                  </>
                )}
                <button type="submit" disabled={saving || (mode === 'cookies' ? !cookies.trim() : (!email || !password))} className="btn-primary w-full flex items-center justify-center gap-2">
                  {saving ? <><Loader2 size={15} style={{ animation: 'spin 1s linear infinite' }} /> Connecting…</> : 'Connect Hudl'}
                </button>
              </form>
            )}

            {msg && (
              <div className={`mt-3 text-sm rounded-lg p-3 ${msg.kind === 'ok' ? 'bg-green-500/10 text-green-400' : 'bg-red-400/10 text-red-400'}`}>
                {msg.text}
              </div>
            )}
          </div>

          {/* YouTube card */}
          <div className="card mt-4">
            <div className="flex items-center gap-3 mb-4">
              <div style={{ width: 38, height: 38, borderRadius: 8, background: 'rgba(201,168,76,0.12)', border: '1px solid rgba(201,168,76,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Link2 size={18} style={{ color: '#C9A84C' }} />
              </div>
              <div>
                <div className="font-semibold">YouTube</div>
                <div className="text-xs text-gray-400">Pull YouTube film in HD (YouTube throttles unauthenticated server downloads to 360p)</div>
              </div>
              {youtube && (
                <span style={{ marginLeft: 'auto', fontSize: 11, color: '#2d8c40', display: 'flex', alignItems: 'center', gap: 5 }}>
                  <CheckCircle size={12} /> Connected
                </span>
              )}
            </div>
            {youtube ? (
              <button onClick={handleDisconnectYoutube} className="btn-secondary flex items-center gap-2 text-sm">
                <Trash2 size={14} /> Disconnect
              </button>
            ) : (
              <form onSubmit={handleConnectYoutube} className="space-y-3">
                <div>
                  <label className="label">YouTube cookies (Netscape format)</label>
                  <textarea className="input" style={{ minHeight: 110, fontFamily: 'monospace', fontSize: 11 }}
                    value={ytCookies} onChange={e => setYtCookies(e.target.value)}
                    placeholder={'# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t...'} />
                  <div className="text-xs text-gray-500 mt-1">
                    Log into YouTube in your browser, export cookies with a "cookies.txt" extension, and paste here. Required for HD YouTube imports on our servers.
                  </div>
                </div>
                <button type="submit" disabled={ytSaving || !ytCookies.trim()} className="btn-primary w-full flex items-center justify-center gap-2">
                  {ytSaving ? <><Loader2 size={15} style={{ animation: 'spin 1s linear infinite' }} /> Connecting…</> : 'Connect YouTube'}
                </button>
              </form>
            )}
            {ytMsg && (
              <div className={`mt-3 text-sm rounded-lg p-3 ${ytMsg.kind === 'ok' ? 'bg-green-500/10 text-green-400' : 'bg-red-400/10 text-red-400'}`}>
                {ytMsg.text}
              </div>
            )}
          </div>

          {/* Security note */}
          <div className="mt-4 flex items-start gap-2 text-xs text-gray-500">
            <Shield size={14} style={{ marginTop: 1, flexShrink: 0 }} />
            <span>Your login is encrypted and stored securely. It's used only to import your film from Hudl on your behalf. You can disconnect anytime. If Hudl requires two-factor verification, automatic connect may not work — you can still paste share links or upload files.</span>
          </div>
        </div>
      </main>
    </div>
  )
}
