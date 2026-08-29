import { useState } from 'react'
import { api } from '../api'
import Modal from './Modal.jsx'

/**
 * Point the demo at a vision model.
 *
 * Narration is optional — the pipeline runs without it — so this says plainly what is
 * and is not working rather than leaving an operator to infer it from empty captions.
 */
export default function ModelDialog({ model, onClose }) {
  const [form, setForm] = useState({
    endpoint: model?.endpoint ?? '',
    model: model?.model ?? 'llava-v1.5',
  })
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const save = async (thenClose) => {
    setBusy(true); setResult(null)
    try {
      const r = await api.setModel(form)
      setResult(r)
      if (thenClose && r.ok) onClose()
    } catch (e) {
      setResult({ ok: false, detail: String(e.message) })
    } finally { setBusy(false) }
  }

  return (
    <Modal title="Vision model"
           subtitle="Any OpenAI-compatible endpoint. Leave the endpoint empty to run the demo without narration."
           onClose={onClose}>
      <div className="space-y-2.5">
        <label className="block">
          <span className="label">Endpoint</span>
          <input value={form.endpoint} onChange={set('endpoint')}
                 placeholder="http://host:8080/v1"
                 className="mt-0.5 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5
                            text-sm text-slate-200 outline-none focus:border-indigo-500" />
        </label>
        <label className="block">
          <span className="label">Model</span>
          <input value={form.model} onChange={set('model')}
                 className="mt-0.5 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5
                            text-sm text-slate-200 outline-none focus:border-indigo-500" />
        </label>

        {result && (
          <div className={`rounded border px-2 py-1.5 text-[11px] ${result.ok
            ? 'border-emerald-800 bg-emerald-950/40 text-emerald-300'
            : 'border-rose-800 bg-rose-950/40 text-rose-300'}`}>
            {result.ok ? '✓ ' : '✗ '}{result.detail}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button className="btn-ghost" onClick={() => save(false)} disabled={busy}>
            {busy ? 'Checking…' : 'Test'}
          </button>
          <button className="btn-primary" onClick={() => save(true)} disabled={busy}>Save</button>
        </div>
      </div>
    </Modal>
  )
}
