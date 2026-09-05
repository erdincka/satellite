import { useCallback, useState } from 'react'
import { api } from './api'
import { useLiveState } from './useLiveState'
import AssetDialog from './components/AssetDialog.jsx'
import ConnectionDialog from './components/ConnectionDialog.jsx'
import ModelDialog from './components/ModelDialog.jsx'
import ReplicationLink from './components/ReplicationLink.jsx'
import SitePanel from './components/SitePanel.jsx'
import StepsDialog from './components/StepsDialog.jsx'

const ACCENT = { HQ: '#6366f1', EDGE: '#14b8a6' }

export default function App() {
  const { state, connected } = useLiveState()
  const [dialog, setDialog] = useState(null)
  const [showJob, setShowJob] = useState(false)
  const [toast, setToast] = useState(null)

  const notify = useCallback((text, bad) => {
    setToast({ text, bad })
    setTimeout(() => setToast(null), 4000)
  }, [])

  // The server owns the job; the dialog just watches pushed state.
  const runJob = async (promise) => {
    setShowJob(true)
    try { await promise } catch (e) { setShowJob(false); notify(String(e.message), true) }
  }

  const actions = {
    editConnection: (side) => setDialog({ kind: 'connection', side }),
    setRunning: (side, value) => api.setRunning(side, value).catch((e) => notify(e.message, true)),
    step: (side) => api.step(side).catch((e) => notify(e.message, true)),
    configure: (side) => runJob(api.configure(side)),
    reset: (side) => runJob(api.reset(side)),
  }

  const requestAsset = async (asset) => {
    try {
      await api.request(asset.key)
      notify(`Requested “${asset.title}”`)
    } catch (e) { notify(String(e.message), true) }
  }

  if (!state) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-500">
        {connected ? 'Loading…' : 'Connecting to the server…'}
      </div>
    )
  }

  const hq = state.sites.HQ
  const edge = state.sites.EDGE

  return (
    <div className="flex h-full flex-col">
      <TopBar state={state} connected={connected} notify={notify} onReset={actions.reset}
              onConfigureModel={() => setDialog({ kind: 'model' })} />

      <main className="flex flex-1 flex-col gap-3 overflow-auto p-3 lg:flex-row">
        <SitePanel site={hq} accent={ACCENT.HQ} actions={actions}
                   onSelect={(a) => setDialog({ kind: 'asset', side: 'HQ', asset: a })}
                   onRequest={requestAsset} />

        <ReplicationLink hq={hq} edge={edge} sameCluster={state.sameCluster}
                         link={state.link} notify={notify}
                         connected={!!(hq.connection.host && edge.connection.host)} />

        <SitePanel site={edge} accent={ACCENT.EDGE} actions={actions}
                   onSelect={(a) => setDialog({ kind: 'asset', side: 'EDGE', asset: a })}
                   onRequest={requestAsset} />
      </main>

      {dialog?.kind === 'connection' && (
        <ConnectionDialog side={dialog.side}
                          connection={state.sites[dialog.side].connection}
                          onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === 'asset' && (
        <AssetDialog side={dialog.side} asset={dialog.asset} model={state.model}
                     onRequest={requestAsset} onClose={() => setDialog(null)}
                     onConfigureModel={() => setDialog({ kind: 'model' })} />
      )}
      {dialog?.kind === 'model' && (
        <ModelDialog model={state.model} onClose={() => setDialog(null)} />
      )}
      {showJob && <StepsDialog job={state.job} onClose={() => setShowJob(false)} />}
      {toast && (
        <div className={`fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-md px-3 py-2
                         text-sm shadow-lg ${toast.bad ? 'bg-rose-700 text-white'
                                                       : 'bg-slate-800 text-slate-100'}`}>
          {toast.text}
        </div>
      )}
    </div>
  )
}

function TopBar({ state, connected, notify, onReset, onConfigureModel }) {
  const [pace, setPace] = useState(state.pace.interval)

  const changePace = async (value) => {
    setPace(value)
    try { await api.setPace({ interval: Number(value) }) }
    catch (e) { notify(String(e.message), true) }
  }

  return (
    <header className="flex flex-wrap items-center gap-3 border-b border-slate-800
                       bg-slate-900/80 px-4 py-2">
      <div className="flex items-baseline gap-2">
        <span className="text-sm font-semibold tracking-tight text-slate-100">Satellite</span>
        <span className="hidden text-[11px] text-slate-500 sm:inline">
          core to edge on HPE Ezmeral Data Fabric
        </span>
      </div>

      <div className="ml-auto flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-1.5 text-[11px] text-slate-400">
          Pace
          <input type="range" min="2" max="30" step="1" value={pace}
                 onChange={(e) => changePace(e.target.value)} className="w-24 accent-indigo-500" />
          <span className="w-8 tabular-nums text-slate-300">{pace}s</span>
        </label>

        <span className="text-[11px] text-slate-500">{state.feedSize} sample assets</span>

        <button onClick={onConfigureModel}
                className={`chip ${state.model?.configured ? 'chip-ok' : 'chip-idle'}`}
                title={state.model?.configured
                  ? `Vision model: ${state.model.model} at ${state.model.endpoint}`
                  : 'No vision model configured — click to set one'}>
          {state.model?.configured ? state.model.model : 'no vision model'}
        </button>

        <span className={`chip ${connected ? 'chip-ok' : 'chip-bad'}`}>
          {connected ? 'live' : 'reconnecting'}
        </span>

        {/* Nothing to reset until a cluster is connected, and offering it invites a
            confusing failure on first run. */}
        <div className="flex gap-1">
          <button className="btn-ghost !px-2 !py-1 !text-[11px]" onClick={() => onReset('EDGE')}
                  disabled={!state.sites.EDGE.connection.host}
                  title={state.sites.EDGE.connection.host ? 'Remove everything the edge owns'
                                                          : 'Connect the edge first'}>
            Reset edge
          </button>
          <button className="btn-ghost !px-2 !py-1 !text-[11px]" onClick={() => onReset('HQ')}
                  disabled={!state.sites.HQ.connection.host}
                  title={state.sites.HQ.connection.host ? 'Remove everything HQ owns'
                                                        : 'Connect HQ first'}>
            Reset HQ
          </button>
        </div>
      </div>
    </header>
  )
}
