export default function Modal({ title, subtitle, onClose, children, wide }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4"
         onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
           className={`panel max-h-[88vh] w-full overflow-y-auto bg-slate-900 p-4
                       ${wide ? 'max-w-3xl' : 'max-w-md'}`}>
        <div className="mb-3 flex items-start justify-between gap-4">
          <div>
            <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
            {subtitle && <p className="mt-0.5 text-[11px] text-slate-400">{subtitle}</p>}
          </div>
          <button onClick={onClose}
                  className="shrink-0 rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-200">✕</button>
        </div>
        {children}
      </div>
    </div>
  )
}
