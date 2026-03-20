import { useQuery } from '@tanstack/react-query'
import { healthApi, hypergraphApi, verkleApi } from '../api/client'
import { Activity, Database, Shield, GitBranch } from 'lucide-react'

function StatCard({ label, value, icon: Icon, color }: {
  label: string; value: string | number; icon: any; color: string
}) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
      <div className="flex items-center gap-3">
        <div className={`p-2.5 rounded-lg ${color}`}>
          <Icon size={20} className="text-white" />
        </div>
        <div>
          <p className="text-sm text-slate-500">{label}</p>
          <p className="text-2xl font-bold text-slate-800">{value}</p>
        </div>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const health = useQuery({ queryKey: ['health'], queryFn: healthApi.check, refetchInterval: 5000 })
  const stats = useQuery({ queryKey: ['stats'], queryFn: hypergraphApi.getStats })
  const verkle = useQuery({ queryKey: ['verkle-root'], queryFn: verkleApi.getRoot })
  const partitions = useQuery({ queryKey: ['partitions'], queryFn: hypergraphApi.getPartitions })

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-slate-800 mb-6">VHP Dashboard</h1>

      {/* Health banner */}
      {health.data && (
        <div className={`mb-6 p-4 rounded-lg text-sm font-medium ${
          health.data.status === 'healthy'
            ? 'bg-green-50 text-green-800 border border-green-200'
            : 'bg-red-50 text-red-800 border border-red-200'
        }`}>
          <Activity size={16} className="inline mr-2" />
          System {health.data.status} &mdash; Engine: {health.data.engine_type}
        </div>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          label="Entities"
          value={stats.data?.entities ?? '…'}
          icon={Database}
          color="bg-blue-500"
        />
        <StatCard
          label="Pairwise Edges"
          value={stats.data?.pairwise_edges ?? '…'}
          icon={GitBranch}
          color="bg-emerald-500"
        />
        <StatCard
          label="Hyperedges"
          value={stats.data?.hyperedges ?? '…'}
          icon={Activity}
          color="bg-purple-500"
        />
        <StatCard
          label="Verkle Partitions"
          value={verkle.data?.leaf_count ?? '…'}
          icon={Shield}
          color="bg-amber-500"
        />
      </div>

      {/* Verkle root */}
      {verkle.data && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 mb-6">
          <h2 className="text-lg font-semibold text-slate-700 mb-2">Verkle Root Commitment</h2>
          <code className="text-xs bg-slate-100 p-2 rounded block break-all">{verkle.data.root}</code>
          <p className="text-sm text-slate-500 mt-2">
            Depth: {verkle.data.depth} &middot; Leaves: {verkle.data.leaf_count}
          </p>
        </div>
      )}

      {/* Entity type breakdown */}
      {stats.data && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 mb-6">
          <h2 className="text-lg font-semibold text-slate-700 mb-3">Hypergraph Overview</h2>
          <div className="grid grid-cols-3 gap-3 text-sm">
            <div className="bg-blue-50 rounded p-3 text-center">
              <p className="text-2xl font-bold text-blue-700">{stats.data.entities}</p>
              <p className="text-blue-600">Entities</p>
            </div>
            <div className="bg-emerald-50 rounded p-3 text-center">
              <p className="text-2xl font-bold text-emerald-700">{stats.data.pairwise_edges}</p>
              <p className="text-emerald-600">Pairwise Edges</p>
            </div>
            <div className="bg-purple-50 rounded p-3 text-center">
              <p className="text-2xl font-bold text-purple-700">{stats.data.hyperedges}</p>
              <p className="text-purple-600">Hyperedges</p>
            </div>
          </div>
        </div>
      )}

      {/* Partitions list */}
      {partitions.data && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
          <h2 className="text-lg font-semibold text-slate-700 mb-3">Verkle Tree Partitions</h2>
          <div className="space-y-2">
            {Object.entries(partitions.data).map(([name, info]: [string, any]) => (
              <div key={name} className="flex justify-between items-center p-3 bg-slate-50 rounded-lg text-sm">
                <span className="font-mono text-slate-700">{name}</span>
                <div className="flex gap-4 text-slate-500">
                  <span>{info.entity_count} entities</span>
                  <span>{info.pairwise_count} edges</span>
                  <span>{info.hyperedge_count} hyperedges</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
