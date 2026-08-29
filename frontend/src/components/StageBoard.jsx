import { useEffect, useRef, useState } from 'react'
import { imageUrl } from '../api'

/**
 * A site's pipeline, as columns.
 *
 * An asset is one tile that moves left to right between stages. It is deliberately not
 * one card per stage-event: the point a technical audience needs to see is a single
 * item progressing, not a growing pile of near-identical cards.
 */
/**
 * Stages an asset passes *through* rather than rests in.
 *
 * In one HQ cycle an asset is stored, catalogued and broadcast inside a single loop
 * iteration, so occupancy of these three is essentially always zero — they were three
 * columns permanently reading "idle". They are not slow stages, they are transits, so
 * they get a compact rail showing rate and totals instead of an empty tile bin. The
 * stages where assets genuinely dwell — Broadcast, Available, Delivered — keep their
 * columns, and the pipeline still reads left to right.
 */
const TRANSIT = new Set(['pipeline', 'download', 'record'])

/** How many column positions a set of stages occupies once transits are collapsed. */
export function columnCount(stages) {
  const transits = stages.filter((s) => TRANSIT.has(s.id)).length
  return stages.length - transits + (transits ? 1 : 0)
}

export default function StageBoard({ side, stages, onSelect, onRequest }) {
  const transits = stages.filter((s) => TRANSIT.has(s.id))
  const resting = stages.filter((s) => !TRANSIT.has(s.id))

  return (
    <div className="flex gap-2 overflow-x-auto pb-1">
      {transits.length > 0 && <TransitRail stages={transits} />}
      {resting.map((stage) => (
        <Column key={stage.id} side={side} stage={stage}
                onSelect={onSelect} onRequest={onRequest} />
      ))}
    </div>
  )
}

/**
 * The transit stages, stacked.
 *
 * Each step pulses when its total advances, which is the only honest way to show a
 * stage nothing ever sits in: you see the throughput, not a phantom queue.
 */
function TransitRail({ stages }) {
  const previous = useRef({})
  const [pulsing, setPulsing] = useState({})

  useEffect(() => {
    const moved = {}
    for (const stage of stages) {
      if (previous.current[stage.id] !== undefined && stage.total > previous.current[stage.id]) {
        moved[stage.id] = true
      }
      previous.current[stage.id] = stage.total
    }
    if (Object.keys(moved).length) {
      setPulsing(moved)
      const timer = setTimeout(() => setPulsing({}), 600)
      return () => clearTimeout(timer)
    }
  }, [stages])

  return (
    <div className="flex min-w-[7rem] flex-1 flex-col gap-1.5">
      <div className="rounded-md bg-gradient-to-r from-slate-700/80 to-slate-600/60 px-2 py-1"
           title="Stages an asset passes straight through on its way to being broadcast">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-white">
          Processing
        </span>
      </div>

      <div className="flex flex-col gap-1.5">
        {stages.map((stage) => (
          <div key={stage.id} title={stage.help}
               className={`rounded-md border px-2 py-1.5 transition-colors duration-300
                           ${pulsing[stage.id]
                             ? 'border-indigo-500/70 bg-indigo-500/15'
                             : 'border-slate-800 bg-slate-900/70'}`}>
            <div className="flex items-baseline justify-between gap-1">
              <span className="truncate text-[10px] uppercase tracking-wide text-slate-400">
                {stage.label}
              </span>
              <span className="shrink-0 text-[11px] font-bold tabular-nums text-slate-200">
                {stage.total}
              </span>
            </div>
            <div className="mt-1 h-0.5 overflow-hidden rounded-full bg-slate-800">
              <span className={`block h-full rounded-full bg-indigo-400 transition-all duration-500
                                ${pulsing[stage.id] ? 'w-full' : 'w-0'}`} />
            </div>
          </div>
        ))}
      </div>

      <p className="px-0.5 text-[9px] leading-snug text-slate-600">
        Passed through, not queued — an asset clears all three in one cycle.
      </p>
    </div>
  )
}

const TONE = {
  pipeline:  'from-indigo-600/80 to-indigo-500/60',
  download:  'from-sky-600/80 to-sky-500/60',
  record:    'from-teal-600/80 to-teal-500/60',
  broadcast: 'from-emerald-600/80 to-emerald-500/60',
  request:   'from-amber-600/80 to-amber-500/60',
  response:  'from-orange-600/80 to-orange-500/60',
  receive:   'from-indigo-600/80 to-indigo-500/60',
  failed:    'from-rose-700/80 to-rose-600/60',
}

function Column({ side, stage, onSelect, onRequest }) {
  return (
    // Narrow enough that HQ's six stages fit side by side within one site panel at a
    // typical laptop width; flex-1 lets them grow on anything larger.
    <div className="flex min-w-[5.5rem] flex-1 flex-col gap-1.5">
      <div className={`rounded-md bg-gradient-to-r ${TONE[stage.id] ?? TONE.pipeline}
                       px-2 py-1 flex items-center justify-between gap-1`}
           title={stage.help}>
        <span className="truncate text-[11px] font-semibold uppercase tracking-wide text-white">
          {stage.label}
        </span>
        {/* The count is what a presenter quotes, so it never gets truncated away. */}
        <span className="shrink-0 text-[11px] font-bold tabular-nums text-white/90">
          {stage.total}
        </span>
      </div>

      <div className="flex flex-col gap-1.5 overflow-y-auto pr-0.5" style={{ maxHeight: '46vh' }}>
        {stage.assets.length === 0 && (
          <div className="rounded-md border border-dashed border-slate-800 py-3 text-center
                          text-[10px] text-slate-600">idle</div>
        )}
        {stage.assets.map((asset) => (
          <Tile key={asset.key} side={side} asset={asset}
                onSelect={onSelect} onRequest={onRequest} />
        ))}
      </div>
    </div>
  )
}

/**
 * Whether this site actually holds the image yet.
 *
 * At HQ the bytes exist from Stored onward; at the edge only once Delivered — before
 * that the edge has the description and nothing else, which is the whole point of the
 * demo. Gating on this avoids requesting images that cannot exist, and makes the
 * asymmetry visible rather than showing a broken-image box.
 */
function holdsImage(side, stage) {
  if (stage === 'failed' || stage === 'pipeline') return false
  return side === 'HQ' ? true : stage === 'response'
}

function Tile({ side, asset, onSelect, onRequest }) {
  const failed = asset.stage === 'failed'
  const requestable = side === 'EDGE' && asset.stage === 'receive'
  const withImage = holdsImage(side, asset.stage)

  return (
    <button
      onClick={() => onSelect(asset)}
      // shrink-0 matters: tiles are flex children of a scrolling column, so without it
      // they compress below their content height and clip the title away.
      className={`group animate-arrive shrink-0 overflow-hidden rounded-md border text-left
                  transition hover:border-slate-600 hover:bg-slate-800/60
                  ${failed ? 'border-rose-800/70 bg-rose-950/30' : 'border-slate-800 bg-slate-900/70'}`}
    >
      {withImage ? (
        <img src={imageUrl(side, asset.key)} alt="" loading="lazy"
             className="h-14 w-full object-cover opacity-90 group-hover:opacity-100"
             onError={(e) => { e.currentTarget.style.display = 'none' }} />
      ) : !failed && (
        // Description only — the imagery has not crossed the link yet.
        <div className="flex h-8 items-center justify-center border-b border-slate-800/80
                        bg-slate-950/40 text-[9px] uppercase tracking-wider text-slate-600">
          description only
        </div>
      )}
      <div className="p-1.5">
        <div className="line-clamp-2 text-[11px] font-medium leading-tight text-slate-200">
          {asset.title}
        </div>
        {failed && asset.error && (
          <div className="mt-1 line-clamp-2 text-[10px] text-rose-300">{asset.error}</div>
        )}
        {!failed && asset.analysis && (
          <div className="mt-1 line-clamp-2 text-[10px] text-slate-400">{asset.analysis}</div>
        )}
        {requestable && (
          <span
            role="button" tabIndex={0}
            onClick={(e) => { e.stopPropagation(); onRequest(asset) }}
            className="mt-1.5 block rounded bg-teal-600/90 py-1 text-center text-[10px]
                       font-semibold text-white hover:bg-teal-500"
          >Request image</span>
        )}
      </div>
    </button>
  )
}
