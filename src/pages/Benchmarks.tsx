import { useMutation } from '@tanstack/react-query'
import { benchmarkApi } from '../api/client'
import { useState } from 'react'
import { BarChart3, Shield, Zap, Layers, GitBranch, Network, Timer } from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend, BarChart, Bar, Area,
  ComposedChart,
} from 'recharts'

export default function Benchmarks() {
  const [perfResults, setPerfResults] = useState<any>(null)
  const [proofData, setProofData] = useState<any>(null)
  const [advResults, setAdvResults] = useState<any>(null)
  const [scalData, setScalData] = useState<any>(null)
  const [layerData, setLayerData] = useState<any>(null)
  const [dagData, setDagData] = useState<any>(null)
  const [hgVsPw, setHgVsPw] = useState<any>(null)
  const [buildData, setBuildData] = useState<any>(null)

  const perfMutation = useMutation({ mutationFn: benchmarkApi.performance, onSuccess: setPerfResults })
  const proofMutation = useMutation({ mutationFn: benchmarkApi.proofSizes, onSuccess: setProofData })
  const advMutation = useMutation({ mutationFn: benchmarkApi.adversarial, onSuccess: setAdvResults })
  const scalMutation = useMutation({ mutationFn: benchmarkApi.scalability, onSuccess: setScalData })
  const layerMutation = useMutation({ mutationFn: benchmarkApi.layerOverhead, onSuccess: setLayerData })
  const dagMutation = useMutation({ mutationFn: benchmarkApi.dagComplexity, onSuccess: setDagData })
  const hgMutation = useMutation({ mutationFn: benchmarkApi.hypergraphVsPairwise, onSuccess: setHgVsPw })
  const buildMutation = useMutation({ mutationFn: benchmarkApi.buildTimeComparison, onSuccess: setBuildData })

  const anyPending = perfMutation.isPending || proofMutation.isPending || advMutation.isPending
    || scalMutation.isPending || layerMutation.isPending || dagMutation.isPending
    || hgMutation.isPending || buildMutation.isPending

  const runAll = () => {
    perfMutation.mutate()
    proofMutation.mutate()
    advMutation.mutate()
    scalMutation.mutate()
    layerMutation.mutate()
    dagMutation.mutate()
    hgMutation.mutate()
    buildMutation.mutate()
  }

  return (
    <div className="p-8 max-w-7xl">
      <h1 className="text-2xl font-bold text-slate-800 mb-2">Benchmarks</h1>
      <p className="text-sm text-slate-400 mb-6">Run individual benchmarks or all at once. Results feed directly into Section 5 of the VHP paper.</p>

      {/* ── Button bar ── */}
      <div className="flex flex-wrap gap-2 mb-6">
        <button onClick={runAll} disabled={anyPending}
          className="flex items-center gap-2 px-4 py-2 bg-slate-800 text-white rounded-lg hover:bg-slate-900 disabled:opacity-50 text-sm font-medium">
          <Zap size={14} /> {anyPending ? 'Running…' : 'Run All Benchmarks'}
        </button>
        <div className="w-px bg-slate-300 mx-1" />
        <button onClick={() => perfMutation.mutate()} disabled={perfMutation.isPending}
          className="px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-xs">
          Performance
        </button>
        <button onClick={() => proofMutation.mutate()} disabled={proofMutation.isPending}
          className="px-3 py-1.5 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 text-xs">
          Proof Sizes
        </button>
        <button onClick={() => advMutation.mutate()} disabled={advMutation.isPending}
          className="px-3 py-1.5 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 text-xs">
          Adversarial
        </button>
        <button onClick={() => scalMutation.mutate()} disabled={scalMutation.isPending}
          className="px-3 py-1.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50 text-xs">
          Scalability
        </button>
        <button onClick={() => layerMutation.mutate()} disabled={layerMutation.isPending}
          className="px-3 py-1.5 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50 text-xs">
          Layer Overhead
        </button>
        <button onClick={() => dagMutation.mutate()} disabled={dagMutation.isPending}
          className="px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 text-xs">
          DAG Complexity
        </button>
        <button onClick={() => hgMutation.mutate()} disabled={hgMutation.isPending}
          className="px-3 py-1.5 bg-rose-600 text-white rounded-lg hover:bg-rose-700 disabled:opacity-50 text-xs">
          Hypergraph vs Pairwise
        </button>
        <button onClick={() => buildMutation.mutate()} disabled={buildMutation.isPending}
          className="px-3 py-1.5 bg-cyan-600 text-white rounded-lg hover:bg-cyan-700 disabled:opacity-50 text-xs">
          Build Time
        </button>
      </div>

      {/* ═══════════════  1. Performance  ═══════════════ */}
      {perfResults && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 mb-6">
          <h2 className="text-lg font-semibold text-slate-700 mb-3">
            <Zap size={18} className="inline mr-2 text-blue-600" />Performance Benchmarks
          </h2>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={perfResults.results}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="operation" fontSize={10} angle={-20} textAnchor="end" height={80} />
              <YAxis label={{ value: 'ms', position: 'insideLeft' }} />
              <Tooltip />
              <Bar dataKey="ms" fill="#3b82f6" radius={[4,4,0,0]} />
            </BarChart>
          </ResponsiveContainer>
          <div className="mt-4 space-y-1">
            {perfResults.results.map((r: any, i: number) => (
              <div key={i} className="flex justify-between text-sm">
                <span className="font-mono text-slate-600">{r.operation}</span>
                <span className="font-bold">{r.ms.toFixed(3)} ms</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ═══════════════  2. Proof Sizes  ═══════════════ */}
      {proofData && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 mb-6">
          <h2 className="text-lg font-semibold text-slate-700 mb-3">
            <Shield size={18} className="inline mr-2 text-purple-600" />Verkle vs Merkle Proof Sizes
          </h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={proofData.comparisons}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="leaves" label={{ value: 'Number of Leaves', position: 'insideBottom', offset: -5 }} />
              <YAxis label={{ value: 'Bytes', angle: -90, position: 'insideLeft' }} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="verkle_bytes" name="Verkle" stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="merkle_bytes" name="Merkle" stroke="#ef4444" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
          <p className="text-xs text-slate-400 mt-2">
            Verkle proofs remain constant at ~96 bytes while Merkle proofs grow O(log n). At 1024 leaves, ~70% reduction.
          </p>
        </div>
      )}

      {/* ═══════════════  3. Scalability  ═══════════════ */}
      {scalData && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 mb-6">
          <h2 className="text-lg font-semibold text-slate-700 mb-3">
            <BarChart3 size={18} className="inline mr-2 text-emerald-600" />Scalability — Overhead vs Entity Count
          </h2>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={scalData.results}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="leaves" label={{ value: 'Verkle Leaves', position: 'insideBottom', offset: -5 }} />
              <YAxis label={{ value: 'ms', angle: -90, position: 'insideLeft' }} />
              <Tooltip />
              <Legend />
              <Area type="monotone" dataKey="build_ms" name="Tree Build" stroke="#10b981" fill="#d1fae5" strokeWidth={2} />
              <Line type="monotone" dataKey="proof_gen_ms" name="Proof Gen (avg)" stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="verify_ms" name="Verify (avg)" stroke="#f59e0b" strokeWidth={2} dot={{ r: 3 }} />
            </ComposedChart>
          </ResponsiveContainer>
          <p className="text-xs text-slate-400 mt-2">
            Build time grows linearly; proof generation and verification remain nearly constant per-leaf.
          </p>
        </div>
      )}

      {/* ═══════════════  4. Build Time Comparison  ═══════════════ */}
      {buildData && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 mb-6">
          <h2 className="text-lg font-semibold text-slate-700 mb-3">
            <Timer size={18} className="inline mr-2 text-cyan-600" />Verkle vs Merkle Build & Proof Timing
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div>
              <p className="text-xs font-medium text-slate-500 mb-1 text-center">Build Time</p>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={buildData.results}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="leaves" fontSize={10} />
                  <YAxis fontSize={10} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="verkle_build_ms" name="Verkle" stroke="#3b82f6" strokeWidth={2} />
                  <Line type="monotone" dataKey="merkle_build_ms" name="Merkle" stroke="#ef4444" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500 mb-1 text-center">Proof Generation</p>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={buildData.results}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="leaves" fontSize={10} />
                  <YAxis fontSize={10} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="verkle_proof_ms" name="Verkle" stroke="#3b82f6" strokeWidth={2} />
                  <Line type="monotone" dataKey="merkle_proof_ms" name="Merkle" stroke="#ef4444" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500 mb-1 text-center">Verification</p>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={buildData.results}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="leaves" fontSize={10} />
                  <YAxis fontSize={10} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="verkle_verify_ms" name="Verkle" stroke="#3b82f6" strokeWidth={2} />
                  <Line type="monotone" dataKey="merkle_verify_ms" name="Merkle" stroke="#ef4444" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
          <p className="text-xs text-slate-400 mt-2">
            Side-by-side timing: tree construction, single-proof generation, and verification at varying leaf counts.
          </p>
        </div>
      )}

      {/* ═══════════════  5. Layer Overhead Breakdown  ═══════════════ */}
      {layerData && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 mb-6">
          <h2 className="text-lg font-semibold text-slate-700 mb-3">
            <Layers size={18} className="inline mr-2 text-amber-600" />Layer-by-Layer Overhead (Single Query)
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={layerData.layers} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" label={{ value: 'ms', position: 'insideBottom', offset: -5 }} />
                <YAxis dataKey="layer" type="category" width={170} fontSize={10} />
                <Tooltip />
                <Bar dataKey="ms" radius={[0,4,4,0]}>
                  {layerData.layers.map((_: any, i: number) => {
                    const colors = ['#3b82f6','#3b82f6','#8b5cf6','#8b5cf6','#8b5cf6','#f59e0b','#ef4444']
                    return <rect key={i} fill={colors[i] || '#94a3b8'} />
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <div>
              <div className="space-y-2">
                {layerData.layers.map((l: any, i: number) => {
                  const pct = (l.ms / layerData.total_ms * 100)
                  const colors = ['bg-blue-500','bg-blue-500','bg-purple-500','bg-purple-500','bg-purple-500','bg-amber-500','bg-red-500']
                  return (
                    <div key={i}>
                      <div className="flex justify-between text-xs text-slate-600 mb-0.5">
                        <span>{l.layer}</span>
                        <span>{l.ms.toFixed(3)} ms ({pct.toFixed(1)}%)</span>
                      </div>
                      <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${colors[i] || 'bg-slate-400'}`} style={{ width: `${Math.max(pct, 1)}%` }} />
                      </div>
                    </div>
                  )
                })}
              </div>
              <div className="mt-4 p-3 bg-slate-50 rounded-lg text-sm">
                <span className="font-semibold">Total:</span> {layerData.total_ms.toFixed(3)} ms
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════  6. DAG Complexity  ═══════════════ */}
      {dagData && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 mb-6">
          <h2 className="text-lg font-semibold text-slate-700 mb-3">
            <GitBranch size={18} className="inline mr-2 text-indigo-600" />Provenance DAG Complexity vs Query Breadth
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={dagData.results}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" fontSize={10} />
                <YAxis yAxisId="left" label={{ value: 'Count', angle: -90, position: 'insideLeft' }} />
                <YAxis yAxisId="right" orientation="right" label={{ value: 'ms', angle: 90, position: 'insideRight' }} />
                <Tooltip />
                <Legend />
                <Bar yAxisId="left" dataKey="dag_nodes" name="DAG Nodes" fill="#818cf8" radius={[4,4,0,0]} />
                <Bar yAxisId="left" dataKey="verkle_proofs" name="Verkle Proofs" fill="#c084fc" radius={[4,4,0,0]} />
                <Line yAxisId="right" type="monotone" dataKey="query_ms" name="Query Time (ms)" stroke="#f59e0b" strokeWidth={2} dot={{ r: 4 }} />
              </ComposedChart>
            </ResponsiveContainer>
            <div className="space-y-2">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-slate-500">
                    <th className="py-1.5">Scenario</th>
                    <th className="py-1.5 text-center">Entities</th>
                    <th className="py-1.5 text-center">DAG Nodes</th>
                    <th className="py-1.5 text-center">Depth</th>
                    <th className="py-1.5 text-center">Proofs</th>
                    <th className="py-1.5 text-right">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {dagData.results.map((r: any, i: number) => (
                    <tr key={i} className="border-b border-slate-100">
                      <td className="py-1.5 font-mono">{r.label}</td>
                      <td className="py-1.5 text-center">{r.entities}</td>
                      <td className="py-1.5 text-center font-semibold">{r.dag_nodes}</td>
                      <td className="py-1.5 text-center">{r.dag_depth}</td>
                      <td className="py-1.5 text-center">{r.verkle_proofs}</td>
                      <td className="py-1.5 text-right">{r.query_ms.toFixed(2)} ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════  7. Hypergraph vs Pairwise  ═══════════════ */}
      {hgVsPw && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 mb-6">
          <h2 className="text-lg font-semibold text-slate-700 mb-3">
            <Network size={18} className="inline mr-2 text-rose-600" />Hypergraph vs Pairwise-Only Detection
          </h2>

          {/* Summary banner */}
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div className="p-3 bg-slate-50 rounded-lg text-center">
              <p className="text-3xl font-bold text-slate-400">{hgVsPw.summary.pairwise_detection_rate}%</p>
              <p className="text-xs text-slate-500">Pairwise Detection Rate</p>
            </div>
            <div className="p-3 bg-green-50 rounded-lg text-center">
              <p className="text-3xl font-bold text-green-700">{hgVsPw.summary.hypergraph_detection_rate}%</p>
              <p className="text-xs text-green-600">Hypergraph Detection Rate</p>
            </div>
          </div>

          {/* Scenario comparison table */}
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500">
                <th className="py-2">Scenario</th>
                <th className="py-2 text-center">Entities</th>
                <th className="py-2 text-center">Pairwise Edges</th>
                <th className="py-2 text-center">Hyperedges</th>
                <th className="py-2 text-center">Pairwise Detects?</th>
                <th className="py-2 text-center">Hypergraph Detects?</th>
              </tr>
            </thead>
            <tbody>
              {hgVsPw.comparisons.map((c: any, i: number) => (
                <tr key={i} className="border-b border-slate-100">
                  <td className="py-2 font-medium">{c.scenario}</td>
                  <td className="py-2 text-center">{c.entity_count}</td>
                  <td className="py-2 text-center">{c.pairwise_edges_found}</td>
                  <td className="py-2 text-center font-semibold">{c.hyperedges_found}</td>
                  <td className="py-2 text-center">
                    {c.pairwise_detects_risk
                      ? <span className="text-green-600">✓</span>
                      : <span className="text-red-500">✗</span>}
                  </td>
                  <td className="py-2 text-center">
                    {c.hypergraph_detects_risk
                      ? <span className="text-green-600 font-bold">✓</span>
                      : <span className="text-red-500">✗</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {hgVsPw.comparisons.some((c: any) => c.hyperedge_labels.length > 0) && (
            <div className="mt-3 text-xs text-slate-400">
              <strong>Hyperedges found:</strong>{' '}
              {hgVsPw.comparisons.flatMap((c: any) => c.hyperedge_labels).filter((v: string, i: number, a: string[]) => a.indexOf(v) === i).join(', ')}
            </div>
          )}
        </div>
      )}

      {/* ═══════════════  8. Adversarial Tests  ═══════════════ */}
      {advResults && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 mb-6">
          <h2 className="text-lg font-semibold text-slate-700 mb-3">
            <Shield size={18} className="inline mr-2 text-red-600" />Adversarial Integrity Tests
          </h2>
          <div className={`p-3 rounded-lg mb-4 text-sm font-medium ${
            advResults.all_passed ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'
          }`}>
            {advResults.all_passed ? '✓ All tests passed' : '✗ Some tests failed'}
          </div>
          <div className="space-y-3">
            {advResults.tests.map((t: any, i: number) => (
              <div
                key={i}
                className={`p-3 rounded-lg border text-sm ${
                  t.passed ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'
                }`}
              >
                <div className="flex justify-between items-center">
                  <span className="font-medium">{t.test}</span>
                  <span>{t.passed ? '✓ PASS' : '✗ FAIL'}</span>
                </div>
                <pre className="text-xs mt-2 opacity-70">{JSON.stringify(t.details, null, 2)}</pre>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
