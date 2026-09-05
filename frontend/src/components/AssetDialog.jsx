import { useState } from 'react'
import { api, imageUrl } from '../api'
import Modal from './Modal.jsx'

export default function AssetDialog({ side, asset, model, onClose, onRequest, onConfigureModel }) {
  const [question, setQuestion] = useState('')
  const [thread, setThread] = useState([])
  const [busy, setBusy] = useState(false)

  const ask = async () => {
    const text = question.trim()
    if (!text) return
    setQuestion(''); setBusy(true)
    setThread((t) => [...t, { role: 'you', text }])
    try {
      const { ok, answer } = await api.ask(side, asset.key, text)
      setThread((t) => [...t, { role: 'model', text: answer, ok }])
    } catch (e) {
      setThread((t) => [...t, { role: 'model', text: String(e.message), ok: false }])
    } finally { setBusy(false) }
  }

  return (
    <Modal title={asset.title} subtitle={asset.keywords} onClose={onClose} wide>
      <div className="space-y-3">
        {asset.stage === 'failed' && asset.error && (
          <div className="rounded border border-rose-800 bg-rose-950/40 p-2 text-[12px] text-rose-200">
            {asset.error}
          </div>
        )}

        {(side === 'HQ' ? asset.stage !== 'pipeline' : asset.stage === 'response') ? (
          <img src={imageUrl(side, asset.key)} alt=""
               className="max-h-72 w-full rounded object-contain"
               onError={(e) => { e.currentTarget.style.display = 'none' }} />
        ) : (
          <div className="rounded border border-dashed border-slate-700 py-8 text-center
                          text-[12px] text-slate-500">
            The image is still at HQ — only its description has crossed the link.
          </div>
        )}

        {asset.description && (
          <p className="text-[12px] leading-relaxed text-slate-400">{asset.description}</p>
        )}

        {asset.analysis && (
          <div className="rounded border border-indigo-900/60 bg-indigo-950/30 p-2">
            <div className="label mb-0.5">Vision model narration</div>
            <p className="text-[12px] text-slate-300">{asset.analysis}</p>
          </div>
        )}

        {side === 'EDGE' && asset.stage === 'receive' && (
          <button className="btn-primary w-full"
                  onClick={() => { onRequest(asset); onClose() }}>
            Request this image from HQ
          </button>
        )}

        <div>
          <div className="label mb-1">Ask the vision model</div>
          {!model?.configured ? (
            // Offering an input that can only answer "not configured" is worse than
            // not offering it: say what is missing and how to fix it.
            <div className="rounded border border-slate-800 bg-slate-950/60 px-2 py-2
                            text-[11px] text-slate-500">
              No vision model configured.{' '}
              <button onClick={onConfigureModel}
                      className="text-indigo-400 underline underline-offset-2 hover:text-indigo-300">
                Set one up
              </button>{' '}
              to ask questions about this image.
            </div>
          ) : (
          <>
          <div className="space-y-1.5">
            {thread.map((m, i) => (
              <div key={i} className={`rounded px-2 py-1 text-[12px]
                          ${m.role === 'you' ? 'bg-slate-800 text-slate-200'
                                             : m.ok === false ? 'bg-rose-950/40 text-rose-300'
                                                              : 'bg-slate-900 text-slate-300'}`}>
                {m.text}
              </div>
            ))}
            {busy && <div className="text-[11px] text-slate-500">Thinking…</div>}
          </div>
          <input value={question} onChange={(e) => setQuestion(e.target.value)}
                 onKeyDown={(e) => e.key === 'Enter' && ask()}
                 placeholder="e.g. how many vehicles are visible?"
                 className="mt-1.5 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5
                            text-sm text-slate-200 outline-none focus:border-indigo-500" />
          </>
          )}
        </div>
      </div>
    </Modal>
  )
}
