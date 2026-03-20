import { useQuery } from '@tanstack/react-query'
import { verkleApi, hypergraphApi } from '../api/client'
import { useState, useMemo } from 'react'
import { Shield, CheckCircle, XCircle, AlertTriangle, GitBranch } from 'lucide-react'

interface TreeNode {
  hash: string
  label: string | null
}

const NODE_W = 120
const NODE_H = 56
const LEVEL_GAP = 40

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
                  <div className="text-[9px] font-bold text-blue-600 uppercase tracking-wider">Root</div>
                )}
                <div className="font-mono text-[10px] text-slate-600 leading-tight px-1 break-all">
                  {node.hash}
                </div>
                {node.label && (
                  <div className="text-[9px] font-semibold text-emerald-700 truncate w-full px-1" title={node.label}>
                    {node.label}
                  </div>
                )}
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

export default function Verkle() {
  const root = useQuery({ queryKey: ['verkle-root'], queryFn: verkleApi.getRoot })
  const tree = useQuery({ queryKey: ['verkle-tree'], queryFn: verkleApi.getTree })
  const rootChain = useQuery({ queryKey: ['root-chain'], queryFn: verkleApi.getRootChain })
  const partitions = useQuery({ queryKey: ['partitions'], queryFn: hypergraphApi.getPartitions })

  const [verifyResult, setVerifyResult] = useState<any>(null)
  const [verifying, setVerifying] = useState(false)
  const [tamperResult, setTamperResult] = useState<any>(null)
  const [tampering, setTampering] = useState(false)

  const handleVerify = async (name: string) => {
    setVerifying(true)
    try {
      const res = await verkleApi.verify(name)
      setVerifyResult(res)
    } finally {
      setVerifying(false)
    }
  }

  const handleTamper = async (name: string) => {
    setTampering(true)
    try {
      const res = await verkleApi.tamperDetect(name)
      setTamperResult(res)
    } finally {
      setTampering(false)
    }
  }

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
          <h2 className="text-lg font-semibold text-slate-700 mb-3">Partition Verification</h2>
          <div className="space-y-2">
            {Object.keys(partitions.data).map(name => (
              <div key={name} className="flex justify-between items-center p-3 bg-slate-50 rounded-lg">
                <span className="font-mono text-sm text-slate-700">{name}</span>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleVerify(name)}
                    disabled={verifying}
                    className="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                  >
                    Verify
                  </button>
                  <button
                    onClick={() => handleTamper(name)}
                    disabled={tampering}
                    className="px-3 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
                  >
                    Tamper Test
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Verify result */}
      {verifyResult && (
        <div className={`p-4 rounded-lg mb-6 ${verifyResult.valid ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
          <div className="flex items-center gap-2">
            {verifyResult.valid
              ? <CheckCircle size={18} className="text-green-600" />
              : <XCircle size={18} className="text-red-600" />}
            <span className="font-medium text-sm">
              {verifyResult.partition}: {verifyResult.valid ? 'VALID' : 'INVALID'}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">Proof size: {verifyResult.proof_size_bytes} bytes</p>
        </div>
      )}

      {/* Tamper result */}
      {tamperResult && (
        <div className="bg-amber-50 border border-amber-200 p-4 rounded-lg mb-6">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={18} className="text-amber-600" />
            <span className="font-medium text-sm">Tamper Detection Result</span>
          </div>
          <div className="text-xs space-y-1">
            <p>Valid before tamper: <b>{tamperResult.valid_before_tamper ? '✓' : '✗'}</b></p>
            <p>Root changed: <b>{tamperResult.root_changed ? '✓' : '✗'}</b></p>
            <p>Valid after tamper: <b>{tamperResult.valid_after_tamper ? '✓ (BAD)' : '✗ (GOOD)'}</b></p>
            <p className="font-bold mt-2">
              Tamper detected: {tamperResult.tamper_detected ? '✓ SUCCESS' : '✗ FAILED'}
            </p>
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
