'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { Printer, Download } from 'lucide-react'

interface Game { id: string; title: string; opponent: string | null; sport: string }
interface Cell { avg_points: number; letter: string; n: number }
interface Sheet {
  players: { jersey: string; name: string | null; unit: string | null }[]
  play_types: string[]
  cells: Record<string, Record<string, Cell>>
  player_averages: Record<string, Cell>
  position_group_averages: Record<string, Cell>
}
interface Annotation { id: string; event_id: string; jersey: string | null; note: string }

const GRADE_BG: Record<string, string> = {
  A: 'rgba(45,140,64,0.28)', B: 'rgba(45,140,64,0.15)', C: 'rgba(201,168,76,0.18)',
  D: 'rgba(217,119,6,0.2)', F: 'rgba(229,115,115,0.22)',
}

export default function GradesPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const [games, setGames] = useState<Game[]>([])
  const [gameId, setGameId] = useState('')
  const [sheet, setSheet] = useState<Sheet | null>(null)
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])
  useEffect(() => {
    if (user) api.get('/games').then(r => { setGames(r.data); if (r.data[0]) setGameId(r.data[0].id) }).catch(() => {})
  }, [user])
  useEffect(() => {
    if (!gameId) return
    setLoading(true)
    Promise.all([
      api.get(`/grades/game/${gameId}/sheet`).then(r => setSheet(r.data)).catch(() => setSheet(null)),
      api.get(`/grades/game/${gameId}/annotations`).then(r => setAnnotations(r.data)).catch(() => setAnnotations([])),
    ]).finally(() => setLoading(false))
  }, [gameId])

  async function downloadCsv() {
    try {
      const res = await api.get(`/grades/game/${gameId}/export`, { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }))
      const a = document.createElement('a'); a.href = url; a.download = `grade-sheet-${gameId}.csv`; a.click()
      URL.revokeObjectURL(url)
    } catch { alert('Could not download the grade sheet.') }
  }

  const hasGrades = sheet && sheet.players.length > 0

  return (
    <div className="flex h-screen overflow-hidden grades-page">
      <style>{`@media print { .grades-page { background:#fff !important } .no-print{display:none!important} .g-card{background:#fff!important;color:#111!important;border-color:#ddd!important} .g-cell{color:#111!important} }`}</style>
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-5xl mx-auto">
          <div className="flex items-center justify-between mb-6 no-print">
            <h2 className="text-2xl font-bold">Player Grades</h2>
            {hasGrades && (
              <div className="flex gap-2">
                <button onClick={() => window.print()} className="btn-secondary flex items-center gap-2"><Printer size={16} /> Print / PDF</button>
                <button onClick={downloadCsv} className="btn-primary flex items-center gap-2"><Download size={16} /> CSV</button>
              </div>
            )}
          </div>

          {games.length === 0 ? (
            <div className="card text-center text-gray-400">No games yet. Import and analyze film to see grades.</div>
          ) : (
            <>
              <div className="mb-6 no-print">
                <label className="label">Game</label>
                <select className="input" value={gameId} onChange={e => setGameId(e.target.value)}>
                  {games.map(g => <option key={g.id} value={g.id}>{g.title}{g.opponent ? ` vs ${g.opponent}` : ''}</option>)}
                </select>
              </div>

              {loading ? (
                <p className="text-gray-400">Loading…</p>
              ) : !hasGrades ? (
                <div className="card text-center text-gray-400">
                  No player grades for this game yet. Run a <strong>Deep + Grade</strong> analysis (the opt-in technique-grading pass) to populate this board.
                </div>
              ) : (
                <>
                  <div className="g-card card overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-gray-400 border-b border-gray-700">
                          <th className="py-2 pr-4">Player</th>
                          {sheet!.play_types.map(t => <th key={t} className="py-2 px-2 text-center">{t}</th>)}
                          <th className="py-2 pl-2 text-center">Overall</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sheet!.players.map(p => (
                          <tr key={p.jersey} className="border-b border-gray-800/60">
                            <td className="py-2 pr-4"><span className="font-mono text-gray-400">#{p.jersey}</span> {p.name || ''} <span className="text-xs text-gray-600">{p.unit}</span></td>
                            {sheet!.play_types.map(t => {
                              const c = sheet!.cells[p.jersey]?.[t]
                              return <td key={t} className="py-1 px-2 text-center g-cell" style={c ? { background: GRADE_BG[c.letter] } : {}}>{c ? c.letter : '—'}</td>
                            })}
                            <td className="py-1 pl-2 text-center font-semibold g-cell" style={sheet!.player_averages[p.jersey] ? { background: GRADE_BG[sheet!.player_averages[p.jersey].letter] } : {}}>
                              {sheet!.player_averages[p.jersey]?.letter || '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                      <tfoot>
                        <tr className="border-t border-gray-700 text-gray-400">
                          <td className="py-2 pr-4 font-semibold">Position group avg</td>
                          <td colSpan={sheet!.play_types.length + 1} className="py-2">
                            <div className="flex flex-wrap gap-3">
                              {Object.entries(sheet!.position_group_averages).map(([unit, avg]) => (
                                <span key={unit} className="text-xs g-cell">{unit}: <strong style={{ color: '#f8f6f0' }}>{avg.letter}</strong></span>
                              ))}
                            </div>
                          </td>
                        </tr>
                      </tfoot>
                    </table>
                  </div>

                  {annotations.length > 0 && (
                    <div className="card mt-6 no-print">
                      <div className="font-semibold mb-2">Coach notes</div>
                      <div className="space-y-2">
                        {annotations.map(a => (
                          <div key={a.id} className="text-sm text-gray-300 border-b border-gray-800/60 pb-2">
                            {a.jersey && <span className="font-mono text-gray-500 mr-2">#{a.jersey}</span>}{a.note}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  )
}
