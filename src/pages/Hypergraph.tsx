import { useEffect, useRef, useState } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { hypergraphApi } from '../api/client'
import { Network } from 'vis-network'
import { DataSet } from 'vis-data'
import { ChevronDown, ChevronRight, ChevronLeft, X } from 'lucide-react'

const typeColors: Record<string, string> = {
  drug: '#3b82f6',
  target: '#ef4444',
  enzyme: '#f59e0b',
  transporter: '#8b5cf6',
  carrier: '#22c55e',
  pathway: '#ec4899',
  condition: '#f97316',
  patient: '#14b8a6',
  demographic: '#6b7280',
}

const PAGE_SIZE = 50
const EDGE_PAGE_SIZE = 500

export default function Hypergraph() {
  const containerRef = useRef<HTMLDivElement>(null)
  const networkRef = useRef<Network | null>(null)
  const [selected, setSelected] = useState<any>(null)
  const [page, setPage] = useState(0)
  const [activeTypes, setActiveTypes] = useState<Set<string>>(new Set(['drug', 'target', 'enzyme', 'transporter', 'carrier', 'pathway']))

  const typesParam = Array.from(activeTypes).join(',')

  const stats = useQuery({ queryKey: ['hg-stats'], queryFn: hypergraphApi.getStats })
  const entities = useQuery({
    queryKey: ['entities', page, typesParam],
    queryFn: () => hypergraphApi.getEntities(PAGE_SIZE, page * PAGE_SIZE, typesParam || undefined),
    placeholderData: keepPreviousData,
  })
  const edges = useQuery({
    queryKey: ['edges', page, typesParam],
    queryFn: () => {
      const ids = entities.data?.items?.map((e: any) => e.id)
      if (!ids?.length) return []
      return hypergraphApi.getEdges(EDGE_PAGE_SIZE, 0, ids.join(','))
    },
    enabled: !!entities.data?.items?.length,
    placeholderData: keepPreviousData,
  })
  const hyperedges = useQuery({ queryKey: ['hyperedges'], queryFn: hypergraphApi.getHyperedges })

  const totalEntities = entities.data?.total ?? stats.data?.entities ?? 0
  const totalPages = Math.max(1, Math.ceil(totalEntities / PAGE_SIZE))
  const rangeStart = page * PAGE_SIZE + 1
  const rangeEnd = Math.min((page + 1) * PAGE_SIZE, totalEntities)

  const toggleType = (type: string) => {
    setActiveTypes(prev => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
    setPage(0)
  }

  useEffect(() => {
    if (!containerRef.current || !entities.data?.items || !edges.data || !hyperedges.data) return

    const entityItems: any[] = entities.data.items
    const entityIds = new Set(entityItems.map((e: any) => e.id))

    // Shape & size by entity type
    const typeShapes: Record<string, { shape: string; size: number }> = {
      drug:        { shape: 'dot',      size: 18 },
      target:      { shape: 'triangle', size: 14 },
      enzyme:      { shape: 'diamond',  size: 14 },
      transporter: { shape: 'star',     size: 14 },
      carrier:     { shape: 'hexagon',  size: 12 },
      pathway:     { shape: 'square',   size: 12 },
    }

    // Primary entity nodes
    const nodes: any[] = entityItems.map((e: any) => {
      const ts = typeShapes[e.type] || { shape: 'dot', size: 12 }
      return {
        id: e.id,
        label: e.name || e.id,
        color: typeColors[e.type] || '#94a3b8',
        shape: ts.shape,
        size: ts.size,
        font: { color: '#1e293b', size: 11 },
        title: `${e.type}: ${e.name}`,
      }
    })

    // Auto-add connected nodes from edges that aren't in current entity set
    const connectedIds = new Set<string>()
    edges.data.forEach((e: any) => {
      if (!entityIds.has(e.source_id)) connectedIds.add(e.source_id)
      if (!entityIds.has(e.target_id)) connectedIds.add(e.target_id)
    })

    // Only include hyperedges that overlap with current page entities
    const allNodeIds = new Set([...entityIds, ...connectedIds])
    const relevantHyperedges = hyperedges.data.filter((h: any) =>
      h.entity_ids.some((eid: string) => entityIds.has(eid))
    )
    relevantHyperedges.forEach((h: any) => {
      h.entity_ids.forEach((eid: string) => {
        if (!allNodeIds.has(eid)) {
          connectedIds.add(eid)
          allNodeIds.add(eid)
        }
      })
    })

    // Create lightweight nodes for connected entities (we know their type from the edge relation)
    connectedIds.forEach((id: string) => {
      // Infer type from edge relationship
      let type = 'drug'
      edges.data.forEach((e: any) => {
        if (e.target_id === id) {
          if (e.relation === 'targets') type = 'target'
          else if (e.relation === 'metabolized_by') type = 'enzyme'
          else if (e.relation === 'transported_by') type = 'transporter'
          else if (e.relation === 'carried_by') type = 'carrier'
          else if (e.relation === 'participates_in') type = 'pathway'
        }
        if (e.source_id === id) {
          if (e.relation === 'targets') type = 'drug'
          else if (e.relation === 'metabolized_by') type = 'drug'
        }
      })
      const ts = typeShapes[type] || { shape: 'dot', size: 10 }
      nodes.push({
        id,
        label: id,
        color: typeColors[type] || '#94a3b8',
        shape: ts.shape,
        size: ts.size * 0.7,
        font: { color: '#64748b', size: 9 },
        title: `${type}: ${id}`,
        borderWidth: 1,
        opacity: 0.7,
      })
    })

    // Hyperedge "hub" nodes — only those relevant to the current page
    relevantHyperedges.forEach((h: any) => {
      nodes.push({
        id: `he_${h.id}`,
        label: h.label.replace(/_/g, '\n'),
        color: h.severity >= 0.8 ? '#dc2626' : h.severity >= 0.5 ? '#f59e0b' : '#94a3b8',
        shape: 'square',
        size: 12,
        font: { color: '#fff', size: 9 },
        title: `Hyperedge: ${h.label} (severity: ${h.severity})`,
      })
    })

    // Pairwise edges
    const visEdges: any[] = edges.data.map((e: any, i: number) => ({
      id: `e_${i}`,
      from: e.source_id,
      to: e.target_id,
      label: e.relation.replace(/_/g, ' '),
      color: { color: e.relation === 'interacts_with' ? '#94a3b8' : typeColors[
        e.relation === 'targets' ? 'target' :
        e.relation === 'metabolized_by' ? 'enzyme' :
        e.relation === 'transported_by' ? 'transporter' :
        e.relation === 'carried_by' ? 'carrier' :
        e.relation === 'participates_in' ? 'pathway' : 'drug'
      ] || '#94a3b8', highlight: '#3b82f6' },
      font: { size: 9, color: '#64748b' },
      arrows: 'to',
      smooth: { type: 'curvedCW', roundness: 0.2 },
    }))

    // Hyperedge connections (hub → member entities) — only relevant ones
    relevantHyperedges.forEach((h: any) => {
      h.entity_ids.forEach((eid: string) => {
        visEdges.push({
          id: `he_${h.id}_${eid}`,
          from: `he_${h.id}`,
          to: eid,
          color: { color: h.severity >= 0.8 ? '#dc2626' : '#f59e0b' },
          width: 2,
          dashes: true,
        })
      })
    })

    const network = new Network(containerRef.current, {
      nodes: new DataSet(nodes),
      edges: new DataSet(visEdges),
    }, {
      physics: {
        solver: 'forceAtlas2Based',
        forceAtlas2Based: { gravitationalConstant: -80, springLength: 150 },
        stabilization: { iterations: 200 },
      },
      interaction: { hover: true, tooltipDelay: 100 },
    })

    network.on('click', (params: any) => {
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0]
        if (nodeId.startsWith('he_')) {
          const he = hyperedges.data.find((h: any) => `he_${h.id}` === nodeId)
          setSelected(he ? { type: 'hyperedge', data: he } : null)
        } else {
          const entity = entities.data?.items?.find((e: any) => e.id === nodeId)
          setSelected(entity ? { type: 'entity', data: entity } : null)
        }
      } else {
        setSelected(null)
      }
    })

    networkRef.current = network
    return () => { network.destroy() }
  }, [entities.data?.items, edges.data, hyperedges.data])

  return (
    <div className="flex h-full">
      {/* Graph + pagination header */}
      <div className="flex-1 flex flex-col">
        {/* Pagination bar */}
        <div className="flex items-center justify-between px-4 py-2 bg-slate-50 border-b border-slate-200 text-sm shrink-0">
          <span className="text-slate-600">
            Showing entities <b>{rangeStart}–{rangeEnd}</b> of <b>{totalEntities.toLocaleString()}</b>
            {totalEntities > PAGE_SIZE && (
              <span className="text-slate-400 ml-1">(page {page + 1} of {totalPages})</span>
            )}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={page === 0}
              className="p-1 rounded hover:bg-slate-200 disabled:opacity-30 disabled:cursor-not-allowed"
              title="Previous page"
            >
              <ChevronLeft size={16} />
            </button>
            {/* Quick page jump buttons */}
            {totalPages <= 7 ? (
              Array.from({ length: totalPages }, (_, i) => (
                <button
                  key={i}
                  onClick={() => setPage(i)}
                  className={`w-7 h-7 rounded text-xs font-medium ${
                    i === page ? 'bg-blue-600 text-white' : 'hover:bg-slate-200 text-slate-600'
                  }`}
                >
                  {i + 1}
                </button>
              ))
            ) : (
              <>
                {[0, 1].map(i => (
                  <button key={i} onClick={() => setPage(i)}
                    className={`w-7 h-7 rounded text-xs font-medium ${i === page ? 'bg-blue-600 text-white' : 'hover:bg-slate-200 text-slate-600'}`}
                  >{i + 1}</button>
                ))}
                {page > 3 && <span className="text-slate-400 px-1">…</span>}
                {page > 2 && page < totalPages - 3 && (
                  <button
                    className="w-7 h-7 rounded text-xs font-medium bg-blue-600 text-white"
                  >{page + 1}</button>
                )}
                {page < totalPages - 4 && <span className="text-slate-400 px-1">…</span>}
                {[totalPages - 2, totalPages - 1].map(i => (
                  <button key={i} onClick={() => setPage(i)}
                    className={`w-7 h-7 rounded text-xs font-medium ${i === page ? 'bg-blue-600 text-white' : 'hover:bg-slate-200 text-slate-600'}`}
                  >{i + 1}</button>
                ))}
              </>
            )}
            <button
              onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="p-1 rounded hover:bg-slate-200 disabled:opacity-30 disabled:cursor-not-allowed"
              title="Next page"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>

        {/* Graph canvas */}
        <div className="flex-1 relative">
          <div ref={containerRef} className="absolute inset-0" />
        </div>
      </div>

      {/* Sidebar */}
      <div className="w-96 border-l border-slate-200 bg-white p-4 overflow-auto">
        <h2 className="text-lg font-semibold text-slate-700 mb-4">Hypergraph</h2>

        {/* Selected detail panel */}
        {selected && (
          <div className="mb-6 bg-white rounded-lg border border-blue-200 shadow-sm overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 bg-blue-50 border-b border-blue-200">
              <span className="text-sm font-semibold text-blue-800">
                {selected.type === 'entity' ? 'Entity' : 'Hyperedge'} Detail
              </span>
              <button onClick={() => setSelected(null)} className="text-slate-400 hover:text-slate-600">
                <X size={14} />
              </button>
            </div>
            <div className="p-4 space-y-3">
              {selected.type === 'entity' && (
                <>
                  <DetailRow label="ID" value={selected.data.id} mono />
                  <DetailRow label="Name" value={selected.data.name} />
                  <DetailRow label="Type" value={
                    <span className="inline-flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full" style={{ background: typeColors[selected.data.type] || '#94a3b8' }} />
                      {selected.data.type}
                    </span>
                  } />
                  {selected.data.properties && Object.keys(selected.data.properties).length > 0 && (
                    <div>
                      <p className="text-xs text-slate-400 mb-1">Properties</p>
                      <div className="bg-slate-50 rounded-md p-2 space-y-2 max-h-96 overflow-y-auto">
                        {Object.entries(selected.data.properties).map(([k, v]: [string, any]) => (
                          <div key={k} className="text-xs">
                            <span className="text-slate-500 font-medium">{k.replace(/_/g, ' ')}</span>
                            <p className="text-slate-700 mt-0.5 whitespace-pre-wrap break-words">{String(v)}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
              {selected.type === 'hyperedge' && (
                <>
                  <DetailRow label="ID" value={selected.data.id} mono />
                  <DetailRow label="Label" value={selected.data.label?.replace(/_/g, ' ')} />
                  <DetailRow label="Severity" value={
                    <span className={`font-semibold ${
                      selected.data.severity >= 0.8 ? 'text-red-600' : selected.data.severity >= 0.5 ? 'text-amber-600' : 'text-green-600'
                    }`}>
                      {selected.data.severity}
                    </span>
                  } />
                  <div>
                    <p className="text-xs text-slate-400 mb-1">Member Entities</p>
                    <div className="flex flex-wrap gap-1">
                      {selected.data.entity_ids?.map((id: string) => (
                        <span key={id} className="px-2 py-0.5 bg-blue-50 border border-blue-200 rounded text-xs font-mono text-blue-700">{id}</span>
                      ))}
                    </div>
                  </div>
                  {selected.data.properties && Object.keys(selected.data.properties).length > 0 && (
                    <div>
                      <p className="text-xs text-slate-400 mb-1">Properties</p>
                      <div className="bg-slate-50 rounded-md p-2 space-y-1">
                        {Object.entries(selected.data.properties).map(([k, v]: [string, any]) => (
                          <div key={k} className="flex justify-between text-xs">
                            <span className="text-slate-500">{k}</span>
                            <span className="text-slate-700 font-medium truncate ml-2 max-w-[180px]">{String(v)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        )}

        {/* Legend + type filters */}
        <CollapsibleSection title="Node Types" defaultOpen>
          {stats.data?.entity_type_counts && (() => {
            const typeCounts: Record<string, number> = stats.data.entity_type_counts
            const shapeIcon = (type: string) => {
              const c = typeColors[type] || '#94a3b8'
              const sz = 14
              switch (type) {
                case 'target': // triangle
                  return <svg width={sz} height={sz} viewBox="0 0 14 14"><polygon points="7,1 13,13 1,13" fill={c}/></svg>
                case 'enzyme': // diamond
                  return <svg width={sz} height={sz} viewBox="0 0 14 14"><polygon points="7,0 14,7 7,14 0,7" fill={c}/></svg>
                case 'transporter': // star
                  return <svg width={sz} height={sz} viewBox="0 0 14 14"><polygon points="7,0 9,5 14,5.5 10,9 11.5,14 7,11.5 2.5,14 4,9 0,5.5 5,5" fill={c}/></svg>
                case 'carrier': // hexagon
                  return <svg width={sz} height={sz} viewBox="0 0 14 14"><polygon points="4,0 10,0 14,7 10,14 4,14 0,7" fill={c}/></svg>
                case 'pathway': // square
                  return <svg width={sz} height={sz} viewBox="0 0 14 14"><rect x="1" y="1" width="12" height="12" fill={c}/></svg>
                default: // dot (drug, etc.)
                  return <svg width={sz} height={sz} viewBox="0 0 14 14"><circle cx="7" cy="7" r="6" fill={c}/></svg>
              }
            }
            return Object.entries(typeCounts)
              .sort(([,a], [,b]) => (b as number) - (a as number))
              .map(([type, count]) => (
              <label key={type} className="flex items-center gap-2 mb-1 text-sm cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={activeTypes.has(type)}
                  onChange={() => toggleType(type)}
                  className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 h-3.5 w-3.5"
                />
                {shapeIcon(type)}
                {type} <span className="text-slate-400 text-xs">({(count as number).toLocaleString()})</span>
              </label>
            ))
          })()}
          {hyperedges.data && (() => {
            const hasCritical = hyperedges.data.some((h: any) => h.severity >= 0.8)
            const hasModerate = hyperedges.data.some((h: any) => h.severity >= 0.5 && h.severity < 0.8)
            const hasLow = hyperedges.data.some((h: any) => h.severity < 0.5)
            return (
              <div className="mt-2">
                {hasCritical && (
                  <div className="flex items-center gap-2 mb-1 text-sm">
                    <span className="w-3 h-3 bg-red-600" />
                    Hyperedge (critical)
                  </div>
                )}
                {hasModerate && (
                  <div className="flex items-center gap-2 mb-1 text-sm">
                    <span className="w-3 h-3 bg-amber-500" />
                    Hyperedge (moderate)
                  </div>
                )}
                {hasLow && (
                  <div className="flex items-center gap-2 text-sm">
                    <span className="w-3 h-3 bg-slate-400" />
                    Hyperedge (low)
                  </div>
                )}
              </div>
            )
          })()}
        </CollapsibleSection>

        {/* Hyperedges list — collapsed by default */}
        {hyperedges.data && (
          <CollapsibleSection title={`Hyperedges (${hyperedges.data.length})`} defaultOpen={false}>
            <div className="space-y-2 max-h-80 overflow-auto pr-1">
              {hyperedges.data.map((h: any) => (
                <button
                  key={h.id}
                  onClick={() => setSelected({ type: 'hyperedge', data: h })}
                  className={`w-full text-left p-2 rounded text-xs border transition-colors hover:ring-1 hover:ring-blue-300 ${
                    h.severity >= 0.8 ? 'border-red-200 bg-red-50' : 'border-amber-200 bg-amber-50'
                  } ${selected?.data?.id === h.id ? 'ring-2 ring-blue-400' : ''}`}
                >
                  <p className="font-semibold">{h.label?.replace(/_/g, ' ')}</p>
                  <p className="text-slate-500">{h.entity_ids.join(', ')}</p>
                  <p>Severity: {h.severity}</p>
                </button>
              ))}
            </div>
          </CollapsibleSection>
        )}
      </div>
    </div>
  )
}

/* ─── Helper Components ─────────────────────────────────── */

function CollapsibleSection({ title, defaultOpen = true, children }: {
  title: string; defaultOpen?: boolean; children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="mb-4">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1 w-full text-left text-sm font-medium text-slate-500 hover:text-slate-700 mb-2"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        {title}
      </button>
      {open && <div className="pl-1">{children}</div>}
    </div>
  )
}

function DetailRow({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex justify-between items-start text-sm">
      <span className="text-slate-400 text-xs shrink-0">{label}</span>
      <span className={`text-slate-700 text-right ${mono ? 'font-mono text-xs' : ''}`}>{value}</span>
    </div>
  )
}
