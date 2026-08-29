/**
 * The link between the two sites.
 *
 * This column is the point of the whole demo: descriptions flow outward continuously
 * and cheaply, requests flow back, and the image itself crosses only when a field team
 * asks for it. Everything here comes from Data Fabric's own replication state rather
 * than being inferred from what the app happens to have sent.
 */
export default function ReplicationLink({ hq, edge, sameCluster }) {
  const replication = hq.status?.replication
  const healthy = replication?.ok
  const known = replication !== undefined

  const broadcast = hq.metrics?.counters?.broadcast ?? 0
  const received = edge.metrics?.counters?.received ?? 0
  const requested = edge.metrics?.counters?.requested ?? 0
  const delivered = edge.metrics?.counters?.delivered ?? 0
  const bytes = hq.metrics?.bytesMoved ?? 0

  const flowing = hq.running || edge.running

  return (
    <div className="flex w-full shrink-0 flex-col items-center gap-3 lg:w-44">
      <div className="label">Data Fabric link</div>

      <div className={`chip ${known ? (healthy ? 'chip-ok' : 'chip-bad') : 'chip-idle'}`}>
        <Dot ok={healthy} known={known} />
        {known ? (healthy ? 'Replicating, in sync' : 'Replicating, behind') : 'No replica yet'}
      </div>

      {sameCluster && (
        <div className="rounded border border-amber-700/40 bg-amber-950/30 px-2 py-1
                        text-center text-[10px] leading-snug text-amber-300/90">
          Both sites on one cluster — the separation is by volume, stream and bucket,
          not by geography
        </div>
      )}

      <Lane label="Descriptions" sub="continuous · cheap" direction="right"
            value={broadcast} paired={received} active={flowing} tone="emerald" />
      <Lane label="Requests" sub="on demand" direction="left"
            value={requested} paired={requested} active={flowing} tone="amber" />
      <Lane label="Imagery" sub={humanBytes(bytes)} direction="right"
            value={delivered} paired={delivered} active={delivered > 0} tone="orange" />

      <div className="w-full rounded border border-slate-800 bg-slate-900/50 p-2">
        <div className="label mb-1">Replication detail</div>
        <div className="break-words text-[10px] leading-relaxed text-slate-400">
          {replication?.detail ?? 'Configure HQ to create the replication pair.'}
        </div>
      </div>
    </div>
  )
}

function Lane({ label, sub, direction, value, paired, active, tone }) {
  const colour = { emerald: 'bg-emerald-400', amber: 'bg-amber-400', orange: 'bg-orange-400' }[tone]
  return (
    <div className="w-full">
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
