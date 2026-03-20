import { Routes, Route, Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, Network, Shield, GitBranch, Brain, BarChart3, Stethoscope } from 'lucide-react'
import clsx from 'clsx'
import Dashboard from './pages/Dashboard'
import Hypergraph from './pages/Hypergraph'
import Verkle from './pages/Verkle'
import Provenance from './pages/Provenance'
import Reasoning from './pages/Reasoning'
import Benchmarks from './pages/Benchmarks'
import SymptomChecker from './pages/SymptomChecker'

const navItems = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/hypergraph', label: 'Hypergraph', icon: Network },
  { path: '/verkle', label: 'Verkle Tree', icon: Shield },
  { path: '/provenance', label: 'Provenance DAG', icon: GitBranch },
  { path: '/reasoning', label: 'Reasoning', icon: Brain },
  { path: '/symptom-checker', label: 'Symptom Checker', icon: Stethoscope },
  { path: '/benchmarks', label: 'Benchmarks', icon: BarChart3 },
]

export default function App() {
  const location = useLocation()

  return (
    <div className="flex h-screen bg-slate-50">
      {/* Sidebar */}
      <div className="w-64 bg-slate-900 text-white flex flex-col">
        <div className="p-6">
          <h1 className="text-xl font-bold">VHP</h1>
          <p className="text-xs text-slate-400 mt-1">Verkle-Verified Hypergraph Provenance</p>
        </div>
        <nav className="flex-1 px-3">
          {navItems.map(item => (
            <Link
              key={item.path}
              to={item.path}
              className={clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg mb-1 text-sm transition-colors',
                location.pathname === item.path
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-300 hover:bg-slate-800',
              )}
            >
              <item.icon size={18} />
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="p-4 text-xs text-slate-500">
          VHP v0.1.0 &mdash; Research Prototype
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-auto">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/hypergraph" element={<Hypergraph />} />
          <Route path="/verkle" element={<Verkle />} />
          <Route path="/provenance" element={<Provenance />} />
          <Route path="/reasoning" element={<Reasoning />} />
          <Route path="/symptom-checker" element={<SymptomChecker />} />
          <Route path="/benchmarks" element={<Benchmarks />} />
        </Routes>
      </div>
    </div>
  )
}
