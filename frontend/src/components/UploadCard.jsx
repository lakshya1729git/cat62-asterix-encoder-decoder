import { useState, useRef } from 'react'
import { encodeFile, decodeFile } from '../api/client'

/* ── Icon: upload arrow ─────────────────────────────────────── */
function UploadIcon({ className = '' }) {
  return (
    <svg className={className} xmlns="http://www.w3.org/2000/svg" fill="none"
      viewBox="0 0 24 24" strokeWidth={1.6} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" />
    </svg>
  )
}

/* ── Icon: download arrow ───────────────────────────────────── */
function DownloadIcon({ className = '' }) {
  return (
    <svg className={className} xmlns="http://www.w3.org/2000/svg" fill="none"
      viewBox="0 0 24 24" strokeWidth={1.6} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
    </svg>
  )
}

/* ── Spinner ────────────────────────────────────────────────── */
function Spinner() {
  return (
    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
  )
}

/* ═══════════════════════════════════════════════════════════════
   UploadCard
   ═══════════════════════════════════════════════════════════════ */
function UploadCard() {
  // 'decode' | 'encode'
  const [mode, setMode] = useState('decode')
  const [file, setFile] = useState(null)
  const [isDragging, setIsDragging] = useState(false)
  // 'idle' | 'processing' | 'success' | 'error'
  const [status, setStatus] = useState('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const [resultBlob, setResultBlob] = useState(null)
  const [resultFilename, setResultFilename] = useState('')
  const fileInputRef = useRef(null)

  const busy = status === 'processing'
  const accept = mode === 'decode' ? '.bin,.ast' : '.json'

  /* ── switch mode ── */
  const handleModeChange = (next) => {
    if (busy) return
    setMode(next)
    setFile(null)
    setStatus('idle')
    setErrorMsg('')
    setResultBlob(null)
    setResultFilename('')
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  /* ── file selection ── */
  const applyFile = (f) => {
    if (!f) return
    setFile(f)
    setStatus('idle')
    setErrorMsg('')
    setResultBlob(null)
    setResultFilename('')
  }
  const handleFileChange = (e) => applyFile(e.target.files?.[0] ?? null)

  /* ── drag-and-drop ── */
  const handleDragOver = (e) => { e.preventDefault(); setIsDragging(true) }
  const handleDragLeave = () => setIsDragging(false)
  const handleDrop = (e) => {
    e.preventDefault()
    setIsDragging(false)
    applyFile(e.dataTransfer.files?.[0] ?? null)
  }

  /* ── process ── */
  const handleProcess = async () => {
    if (!file || busy) return
    setStatus('processing')
    setErrorMsg('')
    setResultBlob(null)

    try {
      if (mode === 'decode') {
        const json = await decodeFile(file)
        const blob = new Blob([JSON.stringify(json, null, 2)], { type: 'application/json' })
        setResultBlob(blob)
        setResultFilename('decoded_output.json')
      } else {
        const blob = await encodeFile(file)
        setResultBlob(blob)
        setResultFilename('encoded_cat62.ast')
      }
      setStatus('success')
    } catch (err) {
      setErrorMsg(err.message ?? 'Unknown error')
      setStatus('error')
    }
  }

  /* ── download ── */
  const handleDownload = () => {
    if (!resultBlob) return
    const url = URL.createObjectURL(resultBlob)
    const a = document.createElement('a')
    a.href = url
    a.download = resultFilename
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="
      glass-card
      w-full max-w-md mx-4
      rounded-2xl
      px-8 py-10
      flex flex-col gap-7
      shadow-glow-blue
      transition-all duration-300
    ">

      {/* ── Header ── */}
      <div className="flex flex-col gap-1">
        <h1 className="text-white text-xl font-semibold tracking-wide">
          ASTERIX Processor
        </h1>
        <p className="text-blue-300/60 text-xs tracking-widest uppercase">
          CAT 62 &mdash; Encode / Decode
        </p>
        <div className="mt-2 h-px bg-gradient-to-r from-blue-600/40 via-blue-400/20 to-transparent" />
      </div>

      {/* ── Mode Toggle ── */}
      <div className="flex rounded-xl overflow-hidden border border-blue-800/50 bg-white/[0.02]">
        {[
          { value: 'decode', label: 'Decode CAT62', sub: '.bin' },
          { value: 'encode', label: 'Encode JSON',  sub: '.json' },
        ].map(({ value, label, sub }) => (
          <button
            key={value}
            onClick={() => handleModeChange(value)}
            disabled={busy}
            className={`
              flex-1 flex flex-col items-center justify-center
              py-3 gap-0.5
              text-xs font-medium tracking-wide
              transition-all duration-200
              ${busy ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'}
              ${mode === value
                ? 'bg-blue-600/25 text-white border-b-2 border-blue-400'
                : 'text-blue-300/50 hover:text-blue-200/70 hover:bg-white/[0.03]'
              }
            `}
          >
            <span>{label}</span>
            <span className="text-[10px] opacity-50 font-normal">{sub}</span>
          </button>
        ))}
      </div>

      {/* ── Drop Zone ── */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !busy && fileInputRef.current?.click()}
        className={`
          relative flex flex-col items-center justify-center gap-3
          rounded-xl border border-dashed
          px-6 py-8
          transition-all duration-200
          ${busy
            ? 'cursor-not-allowed opacity-50 border-blue-900/40 bg-white/[0.01]'
            : isDragging
              ? 'cursor-pointer border-blue-400 bg-blue-500/10 scale-[1.01]'
              : 'cursor-pointer border-blue-800/60 bg-white/[0.02] hover:border-blue-600/70 hover:bg-blue-900/10'
          }
        `}
      >
        <UploadIcon className="w-8 h-8 text-blue-400/70" />

        {file ? (
          <div className="flex flex-col items-center gap-1">
            <span className="text-white/90 text-sm font-medium break-all text-center">
              {file.name}
            </span>
            <span className="text-blue-300/50 text-xs">
              {(file.size / 1024).toFixed(1)} KB &bull; click to change
            </span>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-1">
            <span className="text-white/70 text-sm">
              Drop file here or{' '}
              <span className="text-blue-400 underline underline-offset-2">browse</span>
            </span>
            <span className="text-blue-300/40 text-xs">{accept}</span>
          </div>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept={accept}
          onChange={handleFileChange}
          disabled={busy}
          className="hidden"
        />
      </div>

      {/* ── Process Button ── */}
      <button
        onClick={handleProcess}
        disabled={!file || busy}
        className={`
          flex items-center justify-center gap-2
          w-full py-3 rounded-xl
          text-sm font-semibold tracking-wide
          transition-all duration-200
          ${!file || busy
            ? 'bg-blue-900/30 text-blue-500/40 cursor-not-allowed'
            : 'bg-gradient-to-r from-blue-600 to-blue-500 text-white hover:from-blue-500 hover:to-blue-400 hover:shadow-[0_0_20px_2px_rgba(59,130,246,0.35)] active:scale-[0.98]'
          }
        `}
      >
        {busy ? (
          <>
            <Spinner />
            Processing&hellip;
          </>
        ) : (
          <>
            <UploadIcon className="w-4 h-4" />
            Process File
          </>
        )}
      </button>

      {/* ── Status ── */}
      {status === 'processing' && (
        <p className="text-center text-blue-300/60 text-xs tracking-wide">
          Processing&hellip;
        </p>
      )}

      {status === 'success' && (
        <div className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/25">
          <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_6px_2px_rgba(52,211,153,0.5)]" />
          <span className="text-emerald-300 text-xs font-medium tracking-wide">
            Success
          </span>
        </div>
      )}

      {status === 'error' && (
        <div className="flex items-start gap-2 px-4 py-2.5 rounded-lg bg-red-500/10 border border-red-500/25">
          <span className="mt-0.5 w-2 h-2 flex-shrink-0 rounded-full bg-red-400 shadow-[0_0_6px_2px_rgba(248,113,113,0.4)]" />
          <span className="text-red-300 text-xs font-medium tracking-wide break-all">
            {errorMsg || 'Error'}
          </span>
        </div>
      )}

      {/* ── Download Button ── */}
      {status === 'success' && resultBlob && (
        <button
          onClick={handleDownload}
          className="
            flex items-center justify-center gap-2
            w-full py-3 rounded-xl border border-blue-600/50
            text-sm font-medium tracking-wide text-blue-300
            hover:border-blue-400 hover:text-white hover:bg-blue-500/10
            active:scale-[0.98]
            transition-all duration-200
          "
        >
          <DownloadIcon className="w-4 h-4" />
          Download Result
          <span className="text-blue-400/50 text-xs font-normal">
            {resultFilename}
          </span>
        </button>
      )}

    </div>
  )
}

export default UploadCard
