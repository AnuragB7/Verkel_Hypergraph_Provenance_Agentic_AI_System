import { useQuery } from '@tanstack/react-query'
import { provenanceApi } from '../api/client'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'

const typeColors: Record<string, string> = {
  thought: 'bg-blue-100 text-blue-800 border-blue-200',
  action: 'bg-amber-100 text-amber-800 border-amber-200',
  observation: 'bg-green-100 text-green-800 border-green-200',
  conclusion: 'bg-purple-100 text-purple-800 border-purple-200',
}

export default function Provenance() {
  const records = useQuery({ queryKey: ['prov-records'], queryFn: provenanceApi.listRecords })
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null)
  const dag = useQuery({
    queryKey: ['dag', selectedIdx],
    queryFn: () => provenanceApi.getDag(selectedIdx!),
    enabled: selectedIdx !== null,
  })

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-slate-800 mb-6">Provenance DAG (Layer 3)</h1>

      {/* Record list */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 mb-6">
        <h2 className="text-lg font-semibold text-slate-700 mb-3">Reasoning Records</h2>
        {records.data?.length === 0 && (
          <p className="text-sm text-slate-400">
            No records yet. Go to Reasoning page to process a query.
          </p>
        )}
        <div className="space-y-2">
          {records.data?.map((r: any) => (
            <button
              key={r.index}
              onClick={() => setSelectedIdx(r.index)}
              className={`w-full text-left p-3 rounded-lg border text-sm transition-colors ${
                selectedIdx === r.index
                  ? 'bg-blue-50 border-blue-300'
                  : 'bg-slate-50 border-slate-200 hover:bg-slate-100'
              }`}
            >
              <p className="font-medium text-slate-700">{r.query}</p>
              <p className="text-xs text-slate-400 mt-1">
                DAG: {r.dag_nodes} nodes &middot; Depth: {r.dag_depth} &middot;
                {new Date(r.timestamp * 1000).toLocaleString()}
              </p>
            </button>
          ))}
        </div>
      </div>

      {/* DAG visualization */}
      {dag.data && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
          <h2 className="text-lg font-semibold text-slate-700 mb-1">Reasoning Chain</h2>
          <p className="text-sm text-slate-400 mb-4">
            {dag.data.node_count} nodes &middot; Depth {dag.data.depth}
          </p>

          {/* Nodes in order */}
          <div className="space-y-3">
            {dag.data.nodes?.map((node: any) => (
              <div
                key={node.id}
                className={`p-3 rounded-lg border text-sm ${typeColors[node.type] || 'bg-slate-100'}`}
              >
                <div className="flex justify-between items-start mb-1">
                  <span className="font-semibold uppercase text-xs">{node.type}</span>
                  <span className="text-xs opacity-60 font-mono">{node.id}</span>
                </div>
                {node.type === 'conclusion' ? (
                  <div className="prose prose-sm max-w-none prose-headings:text-purple-800 prose-strong:text-purple-900">
                    <ReactMarkdown>{node.content}</ReactMarkdown>
                  </div>
                ) : (
                  <p>{node.content}</p>
                )}
                {node.verkle_proof_count > 0 && (
                  <p className="text-xs mt-1 opacity-70">
                    Verkle proofs: {node.verkle_proof_count}
                  </p>
                )}
                {node.hyperedges_accessed?.length > 0 && (
                  <p className="text-xs mt-1 opacity-70">
                    Hyperedges: {node.hyperedges_accessed.join(', ')}
                  </p>
                )}
                {node.depends_on?.length > 0 && (
                  <p className="text-xs mt-1 opacity-70">
                    Depends on: {node.depends_on.join(', ')}
                  </p>
                )}
                <p className="text-xs mt-1 opacity-50 font-mono">
                  Hash: {node.node_hash?.substring(0, 24)}…
                </p>
              </div>
            ))}
          </div>

          {/* Edges */}
          {dag.data.edges?.length > 0 && (
            <div className="mt-4 text-xs text-slate-400">
              <p className="font-medium mb-1">Causal edges:</p>
              {dag.data.edges.map((e: any, i: number) => (
                <span key={i} className="inline-block mr-3 font-mono">
                  {e.from} → {e.to}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
