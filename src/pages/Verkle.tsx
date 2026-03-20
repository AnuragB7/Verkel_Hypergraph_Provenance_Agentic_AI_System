import { useQuery } from '@tanstack/react-query'
import { verkleApi, hypergraphApi } from '../api/client'
import { useState, useMemo, useCallback } from 'react'
import { Shield, CheckCircle, XCircle, GitBranch, Loader2, Lock, Unlock } from 'lucide-react'

interface TreeNode {
  hash: string
  label: string | null
}

const NODE_W = 140
const NODE_H = 72
const LEVEL_GAP = 36

const PARTITION_SHORT: Record<string, string> = {
  pairwise_interacts_with: 'DDI',
  pairwise_targets: 'Targets',
  pairwise_metabolized_by: 'Enzymes',
  pairwise_transported_by: 'Transporters',
  pairwise_carried_by: 'Carriers',
  pairwise_participates_in: 'Pathways',
  hyperedge_metabolic_conflict: 'Metab. Conflicts',
  hyperedge_polypharmacy_risk: 'Polypharmacy',
}

/** Turn a raw tree label into a friendly display string */
function friendlyLabel(raw: string | null, isLeaf: boolean): string | null {
  if (!raw) return null
  if (isLeaf) return PARTITION_SHORT[raw] || raw.replace(/^(pairwise_|hyperedge_)/, '')
  // Internal: "a + b" or "a + b + a + b + ..." — extract unique partition short names
  const parts = raw.split(' + ').map(p => PARTITION_SHORT[p.trim()] || p.trim().replace(/^(pairwise_|hyperedge_)/, ''))
  const unique = [...new Set(parts)]
  if (unique.length <= 3) return unique.join(' + ')
  return unique.slice(0, 2).join(' + ') + ` +${unique.length - 2} more`
}

function VerkleTreeView({ levels }: { levels: TreeNode[][] }) {
  const [hoveredNode, setHoveredNode] = useState<string | null>(null)

  const getParent = (lvl: number, idx: number): [number, number] | null =>
    lvl <= 0 ? null : [lvl - 1, Math.floor(idx / 2)]

  const getChildren = (lvl: number, idx: number): [number, number][] => {
    if (lvl >= levels.length - 1) return []
    const next = lvl + 1
    const out: [number, number][] = []
    const l = idx * 2, r = idx * 2 + 1
    if (l < levels[next].length) out.push([next, l])
    if (r < levels[next].length) out.push([next, r])
    return out
  }

  // Compute absolute X center for every node, bottom-up
  const positions = useMemo(() => {
    const leafCount = levels[levels.length - 1].length
    const totalW = leafCount * NODE_W
    // pos[level][nodeIdx] = center X
    const pos: number[][] = Array.from({ length: levels.length }, () => [])

    // Leaves: evenly spaced
    for (let i = 0; i < leafCount; i++) {
      pos[levels.length - 1][i] = (i + 0.5) * (totalW / leafCount)
    }
    // Internal levels: center over children
    for (let lvl = levels.length - 2; lvl >= 0; lvl--) {
      for (let i = 0; i < levels[lvl].length; i++) {
        const children = getChildren(lvl, i)
        if (children.length > 0) {
          const childXs = children.map(([cl, ci]) => pos[cl][ci])
          pos[lvl][i] = childXs.reduce((a, b) => a + b, 0) / childXs.length
        } else {
          pos[lvl][i] = (i + 0.5) * (totalW / levels[lvl].length)
        }
      }
    }
    return pos
  }, [levels])

  // Highlighted path (root ↔ hovered)
  const highlightedEdges = useMemo(() => {
    const edgeSet = new Set<string>()
    const nodeSet = new Set<string>()
    if (!hoveredNode) return { edgeSet, nodeSet }
    const [lvl, nd] = hoveredNode.split('-').map(Number)
    // Walk to root
    let cur: [number, number] | null = [lvl, nd]
    while (cur) {
      nodeSet.add(`${cur[0]}-${cur[1]}`)
      const p = getParent(cur[0], cur[1])
      if (p) edgeSet.add(`${p[0]}-${p[1]}:${cur[0]}-${cur[1]}`)
      cur = p
    }
    // Walk to leaves (BFS)
    const q: [number, number][] = [[lvl, nd]]
    while (q.length) {
      const [cl, cn] = q.shift()!
      nodeSet.add(`${cl}-${cn}`)
      for (const child of getChildren(cl, cn)) {
        edgeSet.add(`${cl}-${cn}:${child[0]}-${child[1]}`)
        nodeSet.add(`${child[0]}-${child[1]}`)
        q.push(child)
      }
    }
    return { edgeSet, nodeSet }
  }, [hoveredNode, levels])

  if (!levels || levels.length === 0) return null

  const leafCount = levels[levels.length - 1].length
  const totalW = leafCount * NODE_W
  const totalH = levels.length * NODE_H + (levels.length - 1) * LEVEL_GAP

  // Collect all edges
  const edges: { key: string; x1: number; y1: number; x2: number; y2: number }[] = []
  for (let lvl = 0; lvl < levels.length - 1; lvl++) {
    const parentY = lvl * (NODE_H + LEVEL_GAP) + NODE_H
    const childY = (lvl + 1) * (NODE_H + LEVEL_GAP)
    for (let i = 0; i < levels[lvl].length; i++) {
      for (const [cl, ci] of getChildren(lvl, i)) {
        edges.push({
          key: `${lvl}-${i}:${cl}-${ci}`,
          x1: positions[lvl][i],
          y1: parentY,
          x2: positions[cl][ci],
          y2: childY,
        })
      }
    }
  }

  return (
    <div className="overflow-x-auto">
      <div className="relative" style={{ width: totalW, height: totalH, margin: '0 auto' }}>
        {/* SVG lines layer */}
        <svg className="absolute inset-0" width={totalW} height={totalH} style={{ pointerEvents: 'none' }}>
          {edges.map(e => {
            const isHl = highlightedEdges.edgeSet.has(e.key)
            return (
              <line
                key={e.key}
                x1={e.x1} y1={e.y1} x2={e.x2} y2={e.y2}
                stroke={isHl ? '#3b82f6' : '#cbd5e1'}
                strokeWidth={isHl ? 2.5 : 1}
                className="transition-all duration-150"
              />
            )
          })}
        </svg>

        {/* Node boxes layer */}
        {levels.map((level, levelIdx) => {
          const y = levelIdx * (NODE_H + LEVEL_GAP)
          return level.map((node, nodeIdx) => {
            const cx = positions[levelIdx][nodeIdx]
            const nodeKey = `${levelIdx}-${nodeIdx}`
            const isHl = highlightedEdges.nodeSet.has(nodeKey)
            const isRoot = levelIdx === 0 && level.length === 1
            const isLeaf = levelIdx === levels.length - 1

            return (
              <div
                key={nodeKey}
                className={`
                  absolute flex flex-col items-center justify-center
                  rounded-lg border text-center cursor-default
                  transition-all duration-150
                  ${isRoot
                    ? 'bg-blue-100 border-blue-400 shadow-md'
                    : isLeaf
                      ? 'bg-emerald-50 border-emerald-300'
                      : 'bg-slate-50 border-slate-300'
                  }
                  ${isHl ? 'ring-2 ring-blue-400 shadow-lg scale-105 z-10' : 'z-0'}
                `}
                style={{
                  width: NODE_W - 10,
                  height: NODE_H - 4,
                  left: cx - (NODE_W - 10) / 2,
                  top: y + 2,
                }}
                onMouseEnter={() => setHoveredNode(nodeKey)}
                onMouseLeave={() => setHoveredNode(null)}
              >
                {isRoot && (
                  <div className="text-[8px] font-bold text-blue-600 uppercase tracking-wider">Root Commitment</div>
                )}
                {!isRoot && !isLeaf && (
                  <div className="text-[8px] font-medium text-slate-400 uppercase tracking-wider">Aggregation</div>
                )}
                <div className="font-mono text-[9px] text-slate-500 leading-tight px-1 break-all">
                  {node.hash}
                </div>
                {(() => {
                  const friendly = friendlyLabel(node.label, isLeaf)
                  if (!friendly) return null
                  return (
                    <div
                      className={`text-[9px] font-semibold truncate w-full px-1 ${
                        isLeaf ? 'text-emerald-700' : isRoot ? 'text-blue-700' : 'text-slate-600'
                      }`}
                      title={node.label || ''}
                    >
                      {friendly}
                    </div>
                  )
                })()}
              </div>
            )
          })
        })}
      </div>

      {/* Legend */}
      <div className="flex items-center justify-center gap-6 text-xs text-slate-500 mt-4 pb-2">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded bg-blue-100 border border-blue-400" /> Root
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded bg-slate-50 border border-slate-300" /> Internal
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded bg-emerald-50 border border-emerald-300" /> Leaf (partition)
        </span>
        <span className="text-slate-400 ml-2">Hover a node to trace its proof path</span>
      </div>
    </div>
  )
}

const PARTITION_META: Record<string, { label: string; desc: string }> = {
  pairwise_interacts_with: { label: 'Drug-Drug Interactions', desc: 'Known interactions between drug pairs (DDI) — severity, effects' },
  pairwise_targets: { label: 'Drug → Target', desc: 'Drugs binding to biological targets (proteins, receptors, enzymes)' },
  pairwise_metabolized_by: { label: 'Drug → Enzyme (metabolism)', desc: 'Which enzymes metabolize each drug (e.g. CYP3A4, CYP2D6)' },
  pairwise_transported_by: { label: 'Drug → Transporter', desc: 'Membrane transporters that move drugs across cell barriers' },
  pairwise_carried_by: { label: 'Drug → Carrier', desc: 'Carrier proteins that bind and transport drugs in the bloodstream' },
  pairwise_participates_in: { label: 'Drug → Pathway', desc: 'Metabolic/signaling pathways a drug participates in (e.g. MAPK, mTOR)' },
  hyperedge_metabolic_conflict: { label: 'Metabolic Conflicts', desc: 'Multi-drug hyperedges flagging shared enzyme competition risks' },
  hyperedge_polypharmacy_risk: { label: 'Polypharmacy Risk', desc: 'Multi-drug hyperedges flagging combined risk from drug categories' },
}

export default function Verkle() {
  const root = useQuery({ queryKey: ['verkle-root'], queryFn: verkleApi.getRoot })
  const tree = useQuery({ queryKey: ['verkle-tree'], queryFn: verkleApi.getTree })
  const rootChain = useQuery({ queryKey: ['root-chain'], queryFn: verkleApi.getRootChain })
  const partitions = useQuery({ queryKey: ['partitions'], queryFn: hypergraphApi.getPartitions })

  const [verifyResults, setVerifyResults] = useState<Record<string, any>>({})
  const [tamperResults, setTamperResults] = useState<Record<string, any>>({})
  const [tamperStep, setTamperStep] = useState<Record<string, number>>({})  // 0-4 animation steps
  const [busyPartition, setBusyPartition] = useState<string | null>(null)

  const handleVerify = useCallback(async (name: string) => {
    setBusyPartition(name)
    try {
      const res = await verkleApi.verify(name)
      setVerifyResults(prev => ({ ...prev, [name]: res }))
    } finally {
      setBusyPartition(null)
    }
  }, [])

  const handleVerifyAll = useCallback(async () => {
    if (!partitions.data) return
    setBusyPartition('__all__')
    const names = Object.keys(partitions.data)
    for (const name of names) {
      try {
        const res = await verkleApi.verify(name)
        setVerifyResults(prev => ({ ...prev, [name]: res }))
      } catch { /* skip */ }
    }
    setBusyPartition(null)
  }, [partitions.data])

  const handleTamper = useCallback(async (name: string) => {
    setBusyPartition(name)
    setTamperResults(prev => { const n = { ...prev }; delete n[name]; return n })

    // Step 1: Generate proof
    setTamperStep(prev => ({ ...prev, [name]: 1 }))
    await new Promise(r => setTimeout(r, 600))

    // Step 2: Tampering data
    setTamperStep(prev => ({ ...prev, [name]: 2 }))
    await new Promise(r => setTimeout(r, 800))

    // Step 3: Verifying tampered proof
    setTamperStep(prev => ({ ...prev, [name]: 3 }))

    try {
      const res = await verkleApi.tamperDetect(name)
      // Step 4: Show result
      setTamperStep(prev => ({ ...prev, [name]: 4 }))
      setTamperResults(prev => ({ ...prev, [name]: res }))
    } catch {
      setTamperStep(prev => ({ ...prev, [name]: 0 }))
    } finally {
      setBusyPartition(null)
    }
  }, [])

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-slate-800 mb-6">Verkle Verification (Layer 2)</h1>

      {/* Root info + Tree visualization */}
      {root.data && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 mb-6">
          <div className="flex items-center gap-3 mb-3">
            <Shield size={24} className="text-blue-600" />
            <h2 className="text-lg font-semibold text-slate-700">Root Commitment</h2>
          </div>
          <code className="text-xs bg-slate-100 p-2 rounded block break-all mb-2">{root.data.root}</code>
          <div className="flex items-center gap-4 text-sm text-slate-500">
            <span>Depth: {root.data.depth}</span>
            <span>Leaves: {root.data.leaf_count}</span>
            <span className="text-xs text-slate-400">Constant proof size: ~96 bytes</span>
          </div>
        </div>
      )}

      {/* Verkle Tree Visualization */}
      {tree.data && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 mb-6">
          <div className="flex items-center gap-3 mb-3">
            <GitBranch size={20} className="text-blue-600" />
            <h2 className="text-lg font-semibold text-slate-700">Verkle Tree Structure</h2>
            <span className="text-xs text-slate-400 ml-auto">
              {tree.data.depth} levels &middot; {tree.data.leaf_count} partitions
            </span>
          </div>
          <VerkleTreeView levels={tree.data.levels} />
        </div>
      )}

      {/* Partition verification */}
      {partitions.data && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-slate-700">Partition Verification</h2>
            <button
              onClick={handleVerifyAll}
              disabled={busyPartition !== null}
              className="px-3 py-1.5 text-xs bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50 flex items-center gap-1.5"
            >
              {busyPartition === '__all__' ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle size={12} />}
              Verify All
            </button>
          </div>
          <div className="space-y-2">
            {Object.entries(partitions.data).map(([name, info]: [string, any]) => {
              const vr = verifyResults[name]
              const tr = tamperResults[name]
              const step = tamperStep[name] || 0
              const isBusy = busyPartition === name || busyPartition === '__all__'

              return (
                <div key={name} className="rounded-lg border border-slate-200 overflow-hidden">
                  {/* Partition row */}
                  <div className="flex items-center justify-between p-3 bg-slate-50">
                    <div className="flex items-center gap-3">
                      {/* Verify status icon */}
                      {vr ? (
                        vr.valid
                          ? <CheckCircle size={16} className="text-green-500 shrink-0" />
                          : <XCircle size={16} className="text-red-500 shrink-0" />
                      ) : (
                        <div className="w-4 h-4 rounded-full border-2 border-slate-300 shrink-0" />
                      )}
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-sm text-slate-700">{name}</span>
                          <span className="text-xs text-slate-400">
                            {info.pairwise_count > 0 ? `${info.pairwise_count.toLocaleString()} edges` : ''}
                            {info.pairwise_count > 0 && info.hyperedge_count > 0 ? ' · ' : ''}
                            {info.hyperedge_count > 0 ? `${info.hyperedge_count.toLocaleString()} hyperedges` : ''}
                          </span>
                        </div>
                        {PARTITION_META[name] && (
                          <div className="mt-0.5">
                            <span className="text-xs font-medium text-slate-600">{PARTITION_META[name].label}</span>
                            <span className="text-[10px] text-slate-400 ml-2">{PARTITION_META[name].desc}</span>
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {vr && (
                        <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${
                          vr.valid ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                        }`}>
                          {vr.valid ? 'VALID' : 'INVALID'} &middot; {vr.proof_size_bytes}B proof
                        </span>
                      )}
                      <button
                        onClick={() => handleVerify(name)}
                        disabled={isBusy}
                        className="px-2.5 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 flex items-center gap-1"
                      >
                        {isBusy && busyPartition === name ? <Loader2 size={10} className="animate-spin" /> : <Lock size={10} />}
                        Verify
                      </button>
                      <button
                        onClick={() => handleTamper(name)}
                        disabled={isBusy}
                        className="px-2.5 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50 flex items-center gap-1"
                      >
                        {isBusy && step > 0 ? <Loader2 size={10} className="animate-spin" /> : <Unlock size={10} />}
                        Tamper Test
                      </button>
                    </div>
                  </div>

                  {/* Tamper animation steps */}
                  {step > 0 && (
                    <div className="px-4 py-3 bg-slate-50/80 border-t border-slate-200">
                      {/* Progress bar */}
                      <div className="flex items-center gap-0 mb-4">
                        {[
                          { n: 1, label: 'Generate Proof', color: 'blue' },
                          { n: 2, label: 'Inject Bad Data', color: 'red' },
                          { n: 3, label: 'Re-verify Proof', color: 'amber' },
                          { n: 4, label: 'Result', color: step >= 4 && tr?.tamper_detected ? 'green' : step >= 4 ? 'red' : 'slate' },
                        ].map(({ n, label, color }, i) => (
                          <div key={n} className="contents">
                            <div className="flex flex-col items-center flex-1">
                              <div className={`w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold transition-all duration-300 ${
                                step >= n ? `bg-${color}-500 text-white` : 'bg-slate-200 text-slate-400'
                              } ${step === n && n < 4 ? 'ring-2 ring-offset-1 animate-pulse' : ''}`}
                                style={step >= n ? { backgroundColor: color === 'blue' ? '#3b82f6' : color === 'red' ? '#ef4444' : color === 'amber' ? '#f59e0b' : color === 'green' ? '#22c55e' : '#94a3b8' } : {}}
                              >
                                {n === 4 && step >= 4 ? (tr?.tamper_detected ? '✓' : '✗') : n}
                              </div>
                              <span className="text-[9px] mt-0.5 text-center text-slate-500">{label}</span>
                            </div>
                            {i < 3 && (
                              <div className={`h-0.5 flex-1 -mt-3 transition-all duration-500 ${step > n ? 'bg-slate-400' : 'bg-slate-200'}`} />
                            )}
                          </div>
                        ))}
                      </div>

                      {/* Step-by-step narrative */}
                      <div className="space-y-2 text-xs">
                        {/* Step 1 detail */}
                        {step >= 1 && (
                          <div className={`p-2.5 rounded-lg border transition-all duration-300 ${step === 1 ? 'bg-blue-50 border-blue-200' : 'bg-slate-50 border-slate-200'}`}>
                            <div className="flex items-start gap-2">
                              <span className="text-blue-500 font-bold shrink-0">1.</span>
                              <div className="space-y-1 min-w-0">
                                <p className="text-slate-700">
                                  <b>Generate Verkle proof</b> for partition <code className="bg-slate-200 px-1 rounded text-[10px]">{name}</code>
                                  {' '}({info.pairwise_count} edges, {info.hyperedge_count} hyperedges)
                                </p>
                                <p className="text-slate-500">
                                  Proof captures the leaf commitment + opening path to root. Size: <b>96 bytes</b> (constant regardless of data size).
                                </p>
                                {step >= 4 && tr && (
                                  <div className="flex items-baseline gap-2 mt-1">
                                    <span className="text-slate-400 shrink-0">Leaf hash:</span>
                                    <code className="font-mono text-[10px] text-blue-700 break-all">{tr.original_leaf_hash}</code>
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>
                        )}

                        {/* Step 2 detail */}
                        {step >= 2 && (
                          <div className={`p-2.5 rounded-lg border transition-all duration-300 ${step === 2 ? 'bg-red-50 border-red-200' : 'bg-slate-50 border-slate-200'}`}>
                            <div className="flex items-start gap-2">
                              <span className="text-red-500 font-bold shrink-0">2.</span>
                              <div className="space-y-1 min-w-0">
                                <p className="text-slate-700">
                                  <b>Inject tampered data</b> into partition leaf
                                </p>
                                <p className="text-slate-500">
                                  Replacing the real serialized partition data
                                  {step >= 4 && tr ? <> (<b>{(tr.original_data_size / 1024).toFixed(1)} KB</b> of edge/hyperedge JSON)</> : null}
                                  {' '}with garbage bytes: <code className="bg-red-100 text-red-700 px-1 rounded text-[10px]">{step >= 4 && tr ? tr.tamper_payload : '0x54414d504552'}</code>
                                  {step >= 4 && tr ? <> (<b>{tr.tamper_payload_size} bytes</b>)</> : null}
                                </p>
                                {step >= 4 && tr && (
                                  <div className="flex items-baseline gap-2 mt-1">
                                    <span className="text-slate-400 shrink-0">Tampered leaf hash:</span>
                                    <code className="font-mono text-[10px] text-red-700 break-all">{tr.tampered_leaf_hash}</code>
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>
                        )}

                        {/* Step 3 detail */}
                        {step >= 3 && (
                          <div className={`p-2.5 rounded-lg border transition-all duration-300 ${step === 3 ? 'bg-amber-50 border-amber-200' : 'bg-slate-50 border-slate-200'}`}>
                            <div className="flex items-start gap-2">
                              <span className="text-amber-500 font-bold shrink-0">3.</span>
                              <div className="space-y-1 min-w-0">
                                <p className="text-slate-700">
                                  <b>Re-verify the original proof</b> against the now-tampered tree
                                </p>
                                <p className="text-slate-500">
                                  The proof was generated before tampering. If the tree detected the change,
                                  the proof path no longer reconstructs to the current root &mdash; verification fails.
                                </p>
                                {step >= 4 && tr && (
                                  <div className="space-y-1 mt-1">
                                    <div className="flex items-baseline gap-2">
                                      <span className="text-slate-400 shrink-0">Original root:</span>
                                      <code className="font-mono text-[10px] text-green-700 break-all">{tr.original_root}</code>
                                    </div>
                                    <div className="flex items-baseline gap-2">
                                      <span className="text-slate-400 shrink-0">Tampered root:</span>
                                      <code className="font-mono text-[10px] text-red-700 break-all">{tr.tampered_root}</code>
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>
                        )}

                        {/* Step 4: Result */}
                        {step >= 4 && tr && (
                          <div className={`p-3 rounded-lg border ${
                            tr.tamper_detected ? 'bg-green-50 border-green-300' : 'bg-red-50 border-red-300'
                          }`}>
                            <div className="grid grid-cols-2 gap-x-8 gap-y-1.5 mb-2">
                              <div className="flex justify-between">
                                <span className="text-slate-500">Valid before tamper:</span>
                                <span className={tr.valid_before_tamper ? 'text-green-600 font-bold' : 'text-red-600 font-bold'}>
                                  {tr.valid_before_tamper ? '✓ YES' : '✗ NO'}
                                </span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-slate-500">Root changed:</span>
                                <span className={tr.root_changed ? 'text-green-600 font-bold' : 'text-red-600 font-bold'}>
                                  {tr.root_changed ? '✓ YES' : '✗ NO'}
                                </span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-slate-500">Valid after tamper:</span>
                                <span className={!tr.valid_after_tamper ? 'text-green-600 font-bold' : 'text-red-600 font-bold'}>
                                  {tr.valid_after_tamper ? '✗ YES (bad!)' : '✓ NO (good!)'}
                                </span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-slate-500">Proof size:</span>
                                <span className="font-mono text-slate-700">{tr.proof_size_bytes} bytes</span>
                              </div>
                            </div>
                            <div className={`text-center font-bold text-sm pt-2 border-t ${
                              tr.tamper_detected ? 'border-green-200 text-green-700' : 'border-red-200 text-red-700'
                            }`}>
                              {tr.tamper_detected
                                ? '🛡️ Verkle proof successfully detected the tampered data'
                                : '⚠️ Tamper detection failed — integrity compromised'}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Root chain */}
      {rootChain.data && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
          <h2 className="text-lg font-semibold text-slate-700 mb-3">Temporal Root Chain</h2>
          <p className="text-sm text-slate-500 mb-3">
            Append-only chain of Verkle roots ({rootChain.data.length} entries)
          </p>
          <div className="space-y-2">
            {rootChain.data.entries?.map((entry: any, i: number) => (
              <div key={i} className="flex justify-between text-xs bg-slate-50 p-2 rounded">
                <span className="font-mono">{entry.verkle_root}</span>
                <span className="text-slate-400">{new Date(entry.timestamp * 1000).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
