import Modal from './Modal.jsx'

/** Per-step results from Prepare or Reset, rather than a wall of command output. */
export default function StepsDialog({ title, steps, busy, onClose }) {
  return (
    <Modal title={title} onClose={busy ? () => {} : onClose}>
      {busy && !steps.length && (
        <div className="py-6 text-center text-sm text-slate-400">Working…</div>
      )}
      <ol className="space-y-1">
        {steps.map((step, i) => (
          <li key={i} className="flex items-start gap-2 text-[12px]">
            <span className={step.skipped ? 'text-slate-500'
                                          : step.ok ? 'text-emerald-400' : 'text-rose-400'}>
              {step.skipped ? '—' : step.ok ? '✓' : '✗'}
            </span>
            <span className="w-40 shrink-0 text-slate-300">{step.name}</span>
            <span className="min-w-0 flex-1 break-words text-slate-500">{step.detail}</span>
          </li>
        ))}
      </ol>
      {!busy && (
        <div className="mt-3 flex justify-end">
          <button className="btn-primary" onClick={onClose}>Done</button>
        </div>
      )}
    </Modal>
  )
}
