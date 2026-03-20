import { useQuery } from '@tanstack/react-query'
import { reasoningApi } from '../api/client'
import { useState, useRef, useEffect, useCallback } from 'react'
import { Brain, Play, CheckCircle, XCircle, Loader2, ChevronDown } from 'lucide-react'
import ReactMarkdown from 'react-markdown'

interface StepData {
  type: 'thought' | 'action' | 'observation' | 'conclusion'
  content: string
  id?: string
  hash?: string
  depends_on?: string[]
  verkle_proofs?: number
  streaming: boolean          // true while tokens still arriving
}

interface DoneData {
  verification?: Record<string, boolean>
  verkle_root?: string
  verkle_proofs_count?: number
  dag_nodes?: number
  dag_depth?: number
  record_hash?: string
}

const STEP_STYLES: Record<string, { label: string; bg: string; border: string; text: string; prose: string }> = {
  thought:     { label: 'THOUGHT',     bg: 'bg-blue-50',   border: 'border-blue-300',  text: 'text-blue-800',   prose: 'prose-headings:text-blue-800 prose-strong:text-blue-900' },
  action:      { label: 'ACTION',      bg: 'bg-amber-50',  border: 'border-amber-300', text: 'text-amber-800',  prose: 'prose-headings:text-amber-800 prose-strong:text-amber-900' },
  observation: { label: 'OBSERVATION', bg: 'bg-green-50',  border: 'border-green-300', text: 'text-green-800',  prose: 'prose-headings:text-green-800 prose-strong:text-green-900' },
  conclusion:  { label: 'CONCLUSION',  bg: 'bg-purple-50', border: 'border-purple-300',text: 'text-purple-800', prose: 'prose-headings:text-purple-800 prose-strong:text-purple-900' },
}

export default function Reasoning() {
  const scenarios = useQuery({ queryKey: ['scenarios'], queryFn: reasoningApi.getScenarios })
  const engine = useQuery({ queryKey: ['engine'], queryFn: reasoningApi.getEngine })
  const models = useQuery({ queryKey: ['models'], queryFn: reasoningApi.getModels })

  const [query, setQuery] = useState('')
  const [entityIds, setEntityIds] = useState('')
  const [steps, setSteps] = useState<StepData[]>([])
  const [doneData, setDoneData] = useState<DoneData | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [switching, setSwitching] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [steps, doneData])

  const runStream = useCallback(async (q: string, ids: string[]) => {
    setSteps([])
    setDoneData(null)
    setIsStreaming(true)

    try {
      const resp = await fetch('/api/reasoning/query/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q, entity_ids: ids }),
      })
      const reader = resp.body?.getReader()
      if (!reader) return
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          let evt: any
          try { evt = JSON.parse(line.slice(6)) } catch { continue }

          if (evt.type === 'step_start') {
            // Open a new empty step card
            setSteps(prev => [...prev, { type: evt.step_type, content: '', streaming: true }])
          } else if (evt.type === 'token') {
            // Append token to the last step
            setSteps(prev => {
              const copy = [...prev]
              const last = copy[copy.length - 1]
              if (last) copy[copy.length - 1] = { ...last, content: last.content + evt.text }
              return copy
            })
          } else if (evt.type === 'step_end') {
            // Finalize the last step with metadata
            setSteps(prev => {
              const copy = [...prev]
              const last = copy[copy.length - 1]
              if (last) {
                copy[copy.length - 1] = {
                  ...last,
                  streaming: false,
                  id: evt.id,
                  hash: evt.hash,
                  depends_on: evt.depends_on,
                  verkle_proofs: evt.verkle_proofs,
                }
              }
              return copy
            })
          } else if (evt.type === 'done') {
            setDoneData(evt)
          }
        }
      }
    } finally {
      setIsStreaming(false)
    }
  }, [])

  const handleSubmit = () => {
    if (!query.trim()) return
    const ids = entityIds.split(',').map(s => s.trim()).filter(Boolean)
    runStream(query, ids)
  }

  const handleScenario = (s: any) => {
    setQuery(s.query)
    setEntityIds(s.entity_ids.join(', '))
    runStream(s.query, s.entity_ids)
  }

  const handleSwitchModel = async (model: string) => {
    setSwitching(true)
    try {
      await reasoningApi.switchModel(model)
      engine.refetch()
    } finally {
      setSwitching(false)
    }
  }

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-slate-800 mb-6">Reasoning Pipeline</h1>

      {/* Engine info + model selector */}
      <div className="flex items-center gap-4 mb-6">
        {engine.data && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-2 text-sm flex items-center gap-2">
            <Brain size={16} className="text-blue-600" />
            <span>Engine: <b>{engine.data.engine_type}</b></span>
            {engine.data.model && <span className="text-blue-500">({engine.data.model})</span>}
          </div>
        )}

        {models.data?.models?.length > 0 && (
          <div className="relative">
            <select
              disabled={switching || isStreaming}
              value={engine.data?.model || ''}
              onChange={e => handleSwitchModel(e.target.value)}
              className="appearance-none bg-white border border-slate-300 rounded-lg pl-3 pr-8 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 cursor-pointer"
            >
              <option value="" disabled>Switch model…</option>
              {models.data.models.map((m: string) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
            <ChevronDown size={14} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
          </div>
        )}

        {switching && (
          <span className="text-sm text-slate-500 flex items-center gap-1">
            <Loader2 size={14} className="animate-spin" /> Switching…
          </span>
        )}
      </div>

      {/* Demo scenarios */}
      {scenarios.data && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 mb-6">
          <h2 className="text-lg font-semibold text-slate-700 mb-3">Demo Scenarios</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {scenarios.data.map((s: any, i: number) => (
              <button
                key={i}
                onClick={() => handleScenario(s)}
                disabled={isStreaming}
                className="text-left p-3 rounded-lg border border-slate-200 hover:border-blue-300 hover:bg-blue-50 transition-colors text-sm disabled:opacity-50"
              >
                <p className="font-medium text-slate-700">{s.name}</p>
                <p className="text-xs text-slate-400 mt-1">{s.query}</p>
                <div className="flex gap-1 mt-2 flex-wrap">
                  {s.entity_ids.map((id: string) => (
                    <span key={id} className="px-1.5 py-0.5 bg-slate-100 rounded text-xs font-mono">{id}</span>
                  ))}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Custom query */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 mb-6">
        <h2 className="text-lg font-semibold text-slate-700 mb-3">Custom Query</h2>
        <div className="space-y-3">
          <div>
            <label className="text-sm text-slate-500 block mb-1">Query</label>
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Is it safe to prescribe…"
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="text-sm text-slate-500 block mb-1">Entity IDs (comma-separated)</label>
            <input
              value={entityIds}
              onChange={e => setEntityIds(e.target.value)}
              placeholder="DB00178, DB00993"
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <button
            onClick={handleSubmit}
            disabled={isStreaming}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm"
          >
            {isStreaming ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            {isStreaming ? 'Reasoning…' : 'Run Query'}
          </button>
        </div>
      </div>

      {/* Streaming reasoning chain */}
      {(steps.length > 0 || isStreaming) && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 mb-6">
          <h2 className="text-lg font-semibold text-slate-700 mb-4">Reasoning Chain</h2>

          <div className="relative pl-6 space-y-0">
            {/* Vertical timeline line */}
            <div className="absolute left-2.5 top-0 bottom-0 w-0.5 bg-slate-200" />

            {steps.map((step, i) => {
              const style = STEP_STYLES[step.type] || STEP_STYLES.thought
              return (
                <div key={i} className="relative pb-4 animate-fade-in">
                  {/* Timeline dot */}
                  <div className={`absolute -left-3.5 top-1 w-3 h-3 rounded-full border-2 ${style.border} ${step.streaming ? 'animate-pulse' : ''} ${style.bg}`} />

                  <div className={`ml-4 p-4 rounded-lg border ${style.border} ${style.bg}`}>
                    <div className="flex items-center justify-between mb-2">
                      <span className={`text-xs font-bold uppercase tracking-wide ${style.text}`}>
                        {style.label}
                        {step.streaming && <Loader2 size={12} className="inline ml-1 animate-spin" />}
                      </span>
                      {step.hash && <span className="text-xs text-slate-400 font-mono">{step.hash}</span>}
                    </div>

                    {/* Markdown-rendered content for ALL step types */}
                    <div className={`text-sm ${style.text} prose prose-sm max-w-none ${style.prose}`}>
                      <ReactMarkdown>{step.content || ''}</ReactMarkdown>
                      {step.streaming && (
                        <span className="inline-block w-1.5 h-4 bg-current animate-pulse ml-0.5 align-text-bottom rounded-sm" />
                      )}
                    </div>

                    {/* Step metadata */}
                    {!step.streaming && (
                      <div className="flex gap-3 mt-2 text-xs text-slate-400">
                        {step.depends_on && step.depends_on.length > 0 && (
                          <span>Depends on: {step.depends_on.map(d => d.slice(0, 8)).join(', ')}</span>
                        )}
                        {step.verkle_proofs !== undefined && step.verkle_proofs > 0 && (
                          <span>Verkle proofs: {step.verkle_proofs}</span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}

            {/* Streaming indicator between steps */}
            {isStreaming && steps.length > 0 && !steps[steps.length - 1]?.streaming && !doneData && (
              <div className="relative pb-4">
                <div className="absolute -left-3.5 top-1 w-3 h-3 rounded-full border-2 border-slate-300 bg-white animate-pulse" />
                <div className="ml-4 p-3 rounded-lg border border-slate-200 bg-slate-50 flex items-center gap-2 text-sm text-slate-500">
                  <Loader2 size={14} className="animate-spin" />
                  Processing next step…
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Verification result */}
      {doneData && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
          <h2 className="text-lg font-semibold text-slate-700 mb-3">Verification</h2>

          <div className="grid grid-cols-2 gap-3 mb-4">
            {Object.entries(doneData.verification || {}).map(([k, v]: [string, any]) => (
              <div key={k} className="flex items-center gap-2 text-sm">
                {v ? <CheckCircle size={14} className="text-green-500" /> : <XCircle size={14} className="text-red-500" />}
                {k.replace(/_/g, ' ')}
              </div>
            ))}
          </div>

          <div className="text-xs text-slate-400 space-y-1">
            <p>Verkle root: <span className="font-mono">{doneData.verkle_root}</span></p>
            <p>Verkle proofs: {doneData.verkle_proofs_count}</p>
            <p>DAG: {doneData.dag_nodes} nodes, depth {doneData.dag_depth}</p>
            <p>Record hash: <span className="font-mono">{doneData.record_hash?.substring(0, 32)}…</span></p>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  )
}
