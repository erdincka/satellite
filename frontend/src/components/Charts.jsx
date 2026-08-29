import { Area, AreaChart, Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from 'recharts'

/**
 * Throughput and latency.
 *
 * Deliberately sparse: during a walkthrough these are read from across a room, so they
 * carry a headline number and a shape, not axes and gridlines.
 */
export default function Charts({ metrics, accent }) {
  const rates = metrics?.rates ?? {}
  const latency = metrics?.latency ?? {}

  const series = mergeRates(rates)
  const throughput = Object.values(rates).flat().reduce((sum, p) => sum + p.v, 0)

  return (
    <div className="grid grid-cols-2 gap-2">
      <Card title="Throughput" value={`${throughput}`} unit="events / 3 min">
        <ResponsiveContainer width="100%" height={44}>
          <AreaChart data={series} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id={`g-${accent}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={accent} stopOpacity={0.55} />
                <stop offset="100%" stopColor={accent} stopOpacity={0} />
              </linearGradient>
            </defs>
            <YAxis hide domain={[0, 'dataMax + 1']} />
            <Tooltip content={<Peek unit="events/s" />} />
            <Area type="monotone" dataKey="v" stroke={accent} strokeWidth={1.5}
                  fill={`url(#g-${accent})`} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </Card>

      <Card title="Asset latency"
            value={latency.p50 != null ? `${latency.p50}s` : '—'}
            unit={latency.p95 != null ? `p95 ${latency.p95}s` : 'feed to broadcast'}>
        <ResponsiveContainer width="100%" height={44}>
          <LineChart data={(metrics?.replicationLag ?? []).map((p) => ({ v: p.v }))}
                     margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
            <YAxis hide domain={[0, 'dataMax + 1']} />
            <Tooltip content={<Peek unit="bytes pending" />} />
            <Line type="monotone" dataKey="v" stroke="#f59e0b" strokeWidth={1.5}
                  dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </Card>
    </div>
  )
}

function Card({ title, value, unit, children }) {
  return (
    <div className="panel p-2">
      <div className="label">{title}</div>
      <div className="flex items-baseline gap-1.5">
        <span className="text-lg font-semibold tabular-nums text-slate-100">{value}</span>
        <span className="text-[10px] text-slate-500">{unit}</span>
      </div>
      {children}
    </div>
  )
}

function Peek({ active, payload, unit }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-200">
      {payload[0].value} {unit}
    </div>
  )
}

/** Sum every stage's per-second rate into one series, so the chart reads as site load. */
function mergeRates(rates) {
  const buckets = new Map()
  for (const points of Object.values(rates)) {
    for (const { t, v } of points) buckets.set(t, (buckets.get(t) ?? 0) + v)
  }
  return [...buckets.entries()].sort((a, b) => a[0] - b[0]).map(([t, v]) => ({ t, v }))
}
