import Charts from './Charts.jsx'
import StageBoard from './StageBoard.jsx'

/** One site: its connection, its controls, its pipeline and its metrics. */
export default function SitePanel({ site, accent, onSelect, onRequest, actions }) {
  const { side, running, ready, status, connection, objects, stages, metrics } = site
  const connected = !!connection.host

  // Width proportional to how many stages the site has: HQ runs six and the edge three,
  // so an even split would squeeze HQ's labels while leaving the edge slack. Growing by
  // stage count gives both sites the same column width, and it self-adjusts when a
  // Failed column appears.
  return (
    <section className="panel flex min-w-0 flex-col gap-3 p-3"
             style={{ flexGrow: stages.length, flexBasis: 0 }}>
      <header className="flex flex-wrap items-center gap-2">
        <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: accent }} />
        <h2 className="text-sm font-semibold text-slate-100">
          {side === 'HQ' ? 'Headquarters' : 'Edge site'}
        </h2>
        <button onClick={() => actions.editConnection(side)}
                className="text-[11px] text-slate-400 underline-offset-2 hover:text-slate-200 hover:underline">
          {connected ? `${connection.username}@${connection.host}` : 'not connected'}
        </button>

        <div className="ml-auto flex items-center gap-1.5">
          {ready && (
            <>
              <button className="btn-ghost !px-2 !py-1 !text-[11px]"
                      onClick={() => actions.step(side)}
                      title="Advance one cycle without running continuously">Step</button>
              <button className={running ? 'btn-danger !px-2 !py-1 !text-[11px]'
                                         : 'btn-primary !px-2 !py-1 !text-[11px]'}
                      onClick={() => actions.setRunning(side, !running)}>
                {running ? 'Pause' : 'Run'}
              </button>
            </>
          )}
        </div>
      </header>

      <StatusRow status={status} />

      {!ready && connected && (
        <div className="flex items-center gap-3 rounded-md border border-amber-700/50
                        bg-amber-950/30 p-3">
          <div className="min-w-0 flex-1">
            <div className="text-xs font-medium text-amber-200">Not prepared yet</div>
            <div className="text-[11px] leading-snug text-amber-300/70">
              {side === 'HQ'
                ? 'Creates HQ’s volume, buckets, streams and the replication pair. Prepare the edge first.'
                : 'Creates the edge’s volume and buckets.'}
            </div>
          </div>
          <button className="btn-primary shrink-0" onClick={() => actions.configure(side)}>
            Prepare
          </button>
        </div>
      )}

      {!connected && (
        <div className="flex items-center gap-3 rounded-md border border-slate-700
                        bg-slate-900/60 p-3">
          <div className="min-w-0 flex-1 text-[11px] text-slate-400">
            No cluster configured for this site.
          </div>
          <button className="btn-primary shrink-0" onClick={() => actions.editConnection(side)}>
            Connect
          </button>
        </div>
      )}

      {ready && <StageBoard side={side} stages={stages} onSelect={onSelect} onRequest={onRequest} />}
      {ready && <Charts metrics={metrics} accent={accent} />}

      <Objects objects={objects} />
    </section>
  )
}

function StatusRow({ status }) {
  const entries = Object.entries(status ?? {})
  if (!entries.length) return <div className="text-[11px] text-slate-600">Checking cluster…</div>
  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.map(([name, { ok, detail }]) => (
        <span key={name} className={`chip ${ok ? 'chip-ok' : 'chip-bad'}`} title={detail}>
          {name}
        </span>
      ))}
    </div>
  )
}

/** What this site owns on the cluster — the thing a technical audience asks about. */
function Objects({ objects }) {
  if (!objects) return null
  const rows = [
    ['Volume', objects.volume],
    ['Stream', objects.stream],
    ['Assets', objects.assetsBucket],
    ['Warehouse', objects.warehouseBucket],
  ]
  return (
    <details className="mt-auto">
      <summary className="cursor-pointer text-[10px] uppercase tracking-wider text-slate-500
                          hover:text-slate-300">Cluster objects</summary>
      <dl className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-[10px] text-slate-500">{k}</dt>
            <dd className="truncate font-mono text-[10px] text-slate-400" title={v}>{v}</dd>
          </div>
        ))}
      </dl>
    </details>
  )
}
