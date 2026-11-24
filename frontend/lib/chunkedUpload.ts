import api from '@/lib/api'
import { shouldTryDirect, transportAfterDirectAttempt } from '@/lib/chunkTransport'

// Resume state for one in-progress film. The file bytes stay on the coach's
// device; this only remembers which upload session to continue.
const RESUME_KEY = 'coachlenz.filmUpload.v1'

const INTERRUPTED =
  'The upload was interrupted. Your film was not saved and your trial game was not used. Select the same file to resume where it left off.'

export type FilmFields = {
  title: string
  sport: string
  team_id?: string
  opponent?: string
  game_date?: string
  is_home?: boolean
  scout_jersey?: string
  opponent_jersey?: string
  scout_attack_dir_h1?: string
  duration_seconds?: number
}

type Saved = {
  token: string
  fileName: string
  fileSize: number
  lastModified: number
  partSize: number
  partCount: number
}

function readSaved(): Saved | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = localStorage.getItem(RESUME_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed?.token || !parsed?.fileName) return null
    return parsed as Saved
  } catch {
    return null
  }
}

function writeSaved(saved: Saved) {
  try { localStorage.setItem(RESUME_KEY, JSON.stringify(saved)) } catch { /* private mode / quota */ }
}

function clearSaved() {
  try { localStorage.removeItem(RESUME_KEY) } catch { /* ignore */ }
}

function matches(saved: Saved, file: File) {
  return saved.fileName === file.name && saved.fileSize === file.size && saved.lastModified === file.lastModified
}

export function peekResume(file: File): boolean {
  const saved = readSaved()
  return !!saved && matches(saved, file)
}

function slicePart(file: File, partNumber: number, partSize: number): Blob {
  const start = (partNumber - 1) * partSize
  return file.slice(start, Math.min(start + partSize, file.size))
}

function putDirect(url: string, body: Blob, onLoaded: (n: number) => void): Promise<boolean> {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', url)
    xhr.timeout = 10 * 60 * 1000
    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable) onLoaded(ev.loaded)
    }
    xhr.onload = () => resolve(xhr.status >= 200 && xhr.status < 300)
    xhr.onerror = () => resolve(false)
    xhr.ontimeout = () => resolve(false)
    xhr.send(body)
  })
}

async function relay(token: string, partNumber: number, body: Blob, onLoaded: (n: number) => void) {
  try {
    await api.put(`/upload/multipart/part/${partNumber}`, body, {
      headers: {
        'Content-Type': 'application/octet-stream',
        'X-Upload-Token': token,
      },
      timeout: 240000,
      maxBodyLength: Infinity,
      maxContentLength: Infinity,
      onUploadProgress: (ev) => onLoaded(ev.loaded),
    })
  } catch (err: any) {
    const detail = err?.response?.data?.detail
    if (typeof detail === 'string' && detail) throw err
    throw new Error(INTERRUPTED)
  }
}

async function mapPool(items: number[], limit: number, fn: (n: number) => Promise<void>) {
  let cursor = 0
  async function worker() {
    while (true) {
      const idx = cursor++
      if (idx >= items.length) return
      await fn(items[idx])
    }
  }
  const workers = Math.max(1, Math.min(limit, items.length))
  if (items.length === 0) return
  await Promise.all(Array.from({ length: workers }, () => worker()))
}

export async function uploadFilmChunked(opts: {
  file: File
  fields: FilmFields
  onProgress: (pct: number) => void
  onDetail?: (text: string) => void
}): Promise<{ id: string }> {
  const { file, fields, onProgress, onDetail } = opts
  const maxBytes = 20 * 1024 * 1024 * 1024
  if (!file.size) throw new Error('Choose a video file to upload.')
  if (file.size > maxBytes) throw new Error('This film is over the 20 GB limit.')

  const payload = {
    ...fields,
    file_name: file.name,
    file_size_bytes: file.size,
    content_type: file.type || 'video/mp4',
    team_id: fields.team_id || undefined,
    game_date: fields.game_date || undefined,
  }

  let token = ''
  let partSize = 0
  let partCount = 0
  let have = new Set<number>()

  const saved = readSaved()
  if (saved && !matches(saved, file)) {
    api.post('/upload/multipart/abort', { upload_token: saved.token }).catch(() => {})
    clearSaved()
  }

  if (saved && matches(saved, file)) {
    try {
      const st = await api.post('/upload/multipart/status', { upload_token: saved.token })
      token = saved.token
      partSize = st.data.part_size
      partCount = st.data.part_count
      have = new Set<number>()
      if (st.data.assembled) {
        for (let n = 1; n <= partCount; n++) have.add(n)
      } else {
        for (const p of st.data.parts || []) have.add(p.part_number)
      }
      onDetail?.(st.data.assembled ? 'Finishing the upload.' : 'Resuming the interrupted upload.')
    } catch {
      clearSaved()
      token = ''
    }
  }

  if (!token) {
    const init = await api.post('/upload/multipart/init', payload)
    token = init.data.upload_token
    partSize = init.data.part_size
    partCount = init.data.part_count
    have = new Set()
    writeSaved({
      token,
      fileName: file.name,
      fileSize: file.size,
      lastModified: file.lastModified,
      partSize,
      partCount,
    })
  }

  const missing: number[] = []
  for (let n = 1; n <= partCount; n++) if (!have.has(n)) missing.push(n)

  const urls = new Map<number, string>()
  let signChain: Promise<void> = Promise.resolve()
  let directOk: boolean | null = null

  function urlFor(partNumber: number): Promise<string> {
    const run = signChain.then(async () => {
      const cached = urls.get(partNumber)
      if (cached) return cached
      const need = [partNumber]
      for (const other of missing) {
        if (need.length >= 8) break
        if (!urls.has(other)) need.push(other)
      }
      const res = await api.post('/upload/multipart/sign', {
        upload_token: token,
        part_numbers: need,
      })
      for (const part of res.data.parts || []) urls.set(part.part_number, part.url)
      const url = urls.get(partNumber)
      if (!url) {
        throw new Error('The upload server did not return a chunk URL. Nothing was saved and your trial game was not used.')
      }
      return url
    })
    signChain = run.then(() => undefined, () => undefined)
    return run
  }

  const filled = new Map<number, number>()
  const inflight = new Map<number, number>()
  const partBytes = (n: number) => Math.min(partSize, file.size - (n - 1) * partSize)
  for (const n of have) filled.set(n, partBytes(n))

  const emit = () => {
    let bytes = 0
    for (const v of filled.values()) bytes += v
    for (const v of inflight.values()) bytes += v
    const pct = file.size ? Math.min(100, Math.round((bytes / file.size) * 100)) : 0
    onProgress(pct)
    const done = filled.size
    onDetail?.(`Uploading chunk ${Math.min(done + 1, partCount)} of ${partCount}`)
  }
  emit()

  await mapPool(missing, 3, async (n) => {
    const body = slicePart(file, n, partSize)
    const report = (loaded: number) => {
      inflight.set(n, Math.min(loaded, body.size))
      emit()
    }
    let sent = false
    if (shouldTryDirect(directOk)) {
      const url = await urlFor(n)
      sent = await putDirect(url, body, report)
      directOk = transportAfterDirectAttempt(sent) === 'direct'
    }
    if (!sent) {
      inflight.set(n, 0)
      await relay(token, n, body, report)
    }
    inflight.delete(n)
    filled.set(n, body.size)
    emit()
  })

  onDetail?.('Finishing the upload.')
  const done = await api.post('/upload/multipart/complete', {
    ...payload,
    upload_token: token,
  })
  clearSaved()
  onProgress(100)
  return { id: done.data.id }
}
