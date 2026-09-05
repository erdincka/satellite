import { useState } from 'react'
import { api } from '../api'
import Modal from './Modal.jsx'

/**
 * Point a site at a cluster, without restarting anything.
 *
 * Test before Save, so an operator can confirm a host mid-session before switching the
 * demo onto it. The password field is never populated from the server.
 */
export default function ConnectionDialog({ side, connection, onClose }) {
  const [form, setForm] = useState({
    host: connection.host ?? '',
    username: connection.username ?? 'mapr',
    password: '',
    rest_port: connection.rest_port ?? 8443,
    s3_port: connection.s3_port ?? 9000,
  })
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const test = async () => {
    setBusy(true); setResult(null)
    try { setResult(await api.testConnection(side, form)) }
    catch (e) { setResult({ error: { ok: false, detail: String(e.message) } }) }
    finally { setBusy(false) }
  }

  const save = async () => {
    setBusy(true)
    try { await api.updateConnection(side, form); onClose() }
    catch (e) { setResult({ error: { ok: false, detail: String(e.message) } }) }
    finally { setBusy(false) }
  }

  return (
    <Modal title={`${side === 'HQ' ? 'Headquarters' : 'Edge'} cluster`}
           subtitle="Both sites may point at the same cluster; they stay separate by volume, stream and bucket."
           onClose={onClose}>
      <div className="space-y-2.5">
        <Field label="Host" value={form.host} onChange={set('host')}
               placeholder="df01.example.com" />
        <div className="grid grid-cols-2 gap-2.5">
          <Field label="User" value={form.username} onChange={set('username')} />
          <Field label="Password" type="password" value={form.password}
                 onChange={set('password')} placeholder="unchanged" />
        </div>
        <div className="grid grid-cols-2 gap-2.5">
          <Field label="REST port" value={form.rest_port} onChange={set('rest_port')} />
          <Field label="S3 port" value={form.s3_port} onChange={set('s3_port')} />
        </div>

        {result && (
          <div className="space-y-1 rounded border border-slate-800 bg-slate-950/60 p-2">
            {Object.entries(result).map(([name, { ok, detail }]) => (
              <div key={name} className="flex gap-2 text-[11px]">
                <span className={ok ? 'text-emerald-400' : 'text-rose-400'}>{ok ? '✓' : '✗'}</span>
                <span className="w-20 shrink-0 text-slate-400">{name}</span>
                <span className="min-w-0 flex-1 break-words text-slate-500">{detail}</span>
              </div>
            ))}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button className="btn-ghost" onClick={test} disabled={busy || !form.host}>
            {busy ? 'Testing…' : 'Test'}
          </button>
          <button className="btn-primary" onClick={save} disabled={busy || !form.host}>Save</button>
        </div>
      </div>
    </Modal>
  )
}

function Field({ label, ...props }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <input {...props}
             className="mt-0.5 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5
                        text-sm text-slate-200 outline-none focus:border-indigo-500" />
    </label>
  )
}
