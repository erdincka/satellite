import { api } from '../api'

/**
 * The link between the two sites.
 *
 * This column is the point of the whole demo: descriptions flow outward continuously
 * and cheaply, requests flow back, and the image itself crosses only when a field team
 * asks for it.
 *
 * It distinguishes what Data Fabric moves from what the application moves. The two
 * stream lanes are genuine replication, read from the cluster's own replica state. The
 * imagery lane is an S3 copy the app performs itself, and says so — a demo that let an
 * audience assume otherwise would be misleading about the one thing it exists to show.
 */
export default function ReplicationLink({ hq, edge, sameCluster, link, notify }) {
  const replication = hq.status?.replication
  const healthy = replication?.ok
  const known = replication !== undefined
  const down = link && !link.open

  const broadcast = hq.metrics?.counters?.broadcast ?? 0
  const received = edge.metrics?.counters?.received ?? 0
  const requested = edge.metrics?.counters?.requested ?? 0
  const delivered = edge.metrics?.counters?.delivered ?? 0
  const bytes = hq.metrics?.bytesMoved ?? 0
  const flowing = (hq.running || edge.running) && !down

  // What has been published but has not reached the other side — the backlog a closed
  // link is accumulating, which is the number worth watching during the demo.
  const queuedOut = Math.max(0, broadcast - received)

  const setMode = async (mode) => {
    try { await api.setLink({ mode }) } catch (e) { notify?.(String(e.message), true) }
  }
  const syncNow = async () => {
    try { await api.syncNow() } catch (e) { notify?.(String(e.message), true) }
  }

  return (
    <div className="flex w-full shrink-0 flex-col items-center gap-3 lg:w-52">
      <div className="label">Data Fabric link</div>

      <div className={`chip ${down ? 'chip-bad' : known ? (healthy ? 'chip-ok' : 'chip-bad') : 'chip-idle'}`}>
        <Dot ok={!down && healthy} known={known} />
        {down ? 'Link down — queueing'
              : known ? (healthy ? 'Replicating, in sync' : 'Replicating, behind')
                      : 'No replica yet'}
      </div>

      <LinkControl link={link} onMode={setMode} onSync={syncNow} queued={queuedOut} />

      {sameCluster && (
        <div className="rounded border border-amber-700/40 bg-amber-950/30 px-2 py-1
                        text-center text-[10px] leading-snug text-amber-300/90">
          Both sites on one cluster — the separation is by volume, stream and bucket,
          not by geography
        </div>
      )}

      <div className="w-full">
        <div className="label mb-1.5">Stream replication</div>
        <Lane label="Descriptions" sub="continuous · cheap" direction="right"
              value={broadcast} active={flowing} tone="emerald" />
        <Lane label="Requests" sub="on demand" direction="left"
              value={requested} active={flowing} tone="amber" />
      </div>

      <div className="w-full">
        <div className="label mb-1.5">Application copy</div>
        <Lane label="Imagery" sub={humanBytes(bytes)} direction="right"
              value={delivered} active={delivered > 0 && !down} tone="orange" />
        <p className="mt-1 text-[9px] leading-snug text-slate-600">
          Copied by the app over S3, not replicated — only the descriptions and requests
          above travel by Data Fabric.
        </p>
      </div>

      <div className="w-full rounded border border-slate-800 bg-slate-900/50 p-2">
        <div className="label mb-1">Replication detail</div>
        <div className="break-words text-[10px] leading-relaxed text-slate-400">
          {link?.lastError ?? replication?.detail ?? 'Prepare HQ to create the replication pair.'}
        </div>
      </div>
    </div>
  )
}

/**
 * Cutting and scheduling the link.
 *
 * Pausing replication is a real cluster operation, so a closed link really does make
 * messages pile up and reopening really does drain them — which is the behaviour worth
 * demonstrating to anyone designing for intermittent connectivity.
 */
function LinkControl({ link, onMode, onSync, queued }) {
  if (!link) return null
  const modes = [
    ['connected', 'On'],
    ['scheduled', 'Scheduled'],
    ['disconnected', 'Cut'],
  ]
  const countdown = link.secondsToChange

  return (
    <div className="w-full rounded border border-slate-800 bg-slate-900/50 p-2">
      <div className="flex overflow-hidden rounded border border-slate-700">
        {modes.map(([mode, label]) => (
          <button key={mode} onClick={() => onMode(mode)}
                  className={`flex-1 px-1 py-1 text-[10px] font-medium transition
                              ${link.mode === mode
                                ? mode === 'disconnected'
                                  ? 'bg-rose-700 text-white'
                                  : 'bg-indigo-600 text-white'
                                : 'bg-slate-900 text-slate-400 hover:bg-slate-800'}`}>
            {label}
          </button>
        ))}
      </div>

      {link.mode === 'scheduled' && countdown != null && (
        <div className="mt-1.5 text-center text-[10px] text-slate-400">
          {link.open
            ? `syncing — closes in ${Math.max(0, Math.round(countdown))}s`
            : `next sync in ${Math.max(0, Math.round(countdown))}s`}
        </div>
      )}

      {queued > 0 && !link.open && (
        <div className="mt-1.5 text-center text-[10px] text-amber-300">
          {queued} description{queued === 1 ? '' : 's'} waiting to cross
        </div>
      )}

      {!link.open && (
        <button onClick={onSync}
                className="mt-1.5 w-full rounded bg-slate-800 py-1 text-[10px] font-medium
                           text-slate-200 hover:bg-slate-700">
          Sync now
        </button>
      )}
    </div>
  )
}

function Lane({ label, sub, direction, value, active, tone }) {
  const colour = { emerald: 'bg-emerald-400', amber: 'bg-amber-400', orange: 'bg-orange-400' }[tone]
  return (
    <div className="mb-2 w-full">
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-[11px] font-medium text-slate-300">{label}</span>
        <span className="text-[11px] font-bold tabular-nums text-slate-200">{value}</span>
      </div>
      <div className="relative h-1.5 overflow-hidden rounded-full bg-slate-800">
        {active && (
          <span className={`absolute inset-y-0 w-6 rounded-full ${colour} animate-travel`}
                style={{ animationDirection: direction === 'left' ? 'reverse' : 'normal' }} />
        )}
      </div>
      <div className="mt-0.5 flex justify-between text-[9px] text-slate-500">
        <span>{direction === 'right' ? 'HQ → Edge' : 'Edge → HQ'}</span>
        <span>{sub}</span>
      </div>
    </div>
  )
}

function Dot({ ok, known }) {
  const tone = !known ? 'bg-slate-500' : ok ? 'bg-emerald-400' : 'bg-rose-400'
  return <span className={`h-1.5 w-1.5 rounded-full ${tone} ${known && ok ? 'animate-pulse' : ''}`} />
}

function humanBytes(n) {
  if (!n) return 'none yet'
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / 1024 ** 2).toFixed(1)} MB`
}
