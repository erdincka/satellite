import Modal from './Modal.jsx'

/**
 * Progress for Configure and Reset.
 *
 * Driven by the job in pushed server state rather than one response at the end, so the
 * checklist fills in as the cluster works and the step in flight spins. These take
 * upwards of a minute; a static "Resetting…" gives an operator no way to tell slow from
 * hung.
 */
export default function StepsDialog({ job, onClose }) {
  const steps = job?.steps ?? []
  const running = job?.running
  const title = job?.kind === 'reset'
    ? `Resetting ${job.side}` : `Preparing ${job?.side ?? ''}`
  const failed = steps.filter((s) => !s.ok).length

  return (
    <Modal title={title}
           subtitle={running
             ? 'Working on the cluster — each step appears as it completes'
             : failed ? `${failed} step(s) failed` : 'Done'}
           onClose={running ? () => {} : onClose}>
      <ol className="space-y-1">
        {steps.map((step, i) => (
          <li key={i} className="flex items-start gap-2 text-[12px]">
            <span className={step.skipped ? 'text-slate-500'
                                          : step.ok ? 'text-emerald-400' : 'text-rose-400'}>
              {step.skipped ? '—' : step.ok ? '✓' : '✗'}
            </span>
            <span className="w-44 shrink-0 text-slate-300">{step.name}</span>
            <span className="min-w-0 flex-1 break-words text-slate-500">{step.detail}</span>
          </li>
        ))}
        {running && (
          <li className="flex items-center gap-2 pt-1 text-[12px] text-slate-400">
            <Spinner />
            <span>{steps.length ? 'next step…' : 'starting…'}</span>
          </li>
        )}
      </ol>

      {job?.error && (
        <div className="mt-2 rounded border border-rose-800 bg-rose-950/40 px-2 py-1.5
                        text-[11px] text-rose-300">{job.error}</div>
      )}

      <div className="mt-3 flex items-center justify-between">
        <span className="text-[10px] text-slate-600">
          {job?.elapsed != null && `${job.elapsed}s`}
        </span>
        <button className="btn-primary" onClick={onClose} disabled={running}>
          {running ? 'Working…' : 'Done'}
        </button>
      </div>
    </Modal>
  )
}

function Spinner() {
  return (
    <svg className="h-3 w-3 animate-spin text-indigo-400" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-90" fill="currentColor"
            d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  )
}
