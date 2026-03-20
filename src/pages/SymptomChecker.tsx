import { useState, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import { Search, Pill, AlertTriangle, ShieldCheck, ChevronDown, ChevronRight, Code2, Loader2, Network, User } from 'lucide-react'

interface DrugCandidate {
  id: string
  name: string
  indication: string
  score?: number
  similarity?: number
  graph_score?: number
  reasons?: string[]
}

interface Interaction {
  drug_a: string
  drug_b: string
  name_a: string
  name_b: string
  severity: string
  description: string
}

interface HyperedgeAlert {
  id: string
  label: string
  severity: number
  overlap: string[]
}

type Phase = 'idle' | 'searching' | 'llm_matching' | 'safety_check' | 'safety_conclusion' | 'done'

const severityColor: Record<string, string> = {
  high: 'text-red-600 bg-red-50 border-red-200',
  moderate: 'text-amber-600 bg-amber-50 border-amber-200',
  low: 'text-green-600 bg-green-50 border-green-200',
  unknown: 'text-slate-600 bg-slate-50 border-slate-200',
}

export default function SymptomChecker() {
  const [symptoms, setSymptoms] = useState('')
  const [age, setAge] = useState('')
  const [gender, setGender] = useState('')
  const [weight, setWeight] = useState('')
  const [phase, setPhase] = useState<Phase>('idle')
  const [candidates, setCandidates] = useState<DrugCandidate[]>([])
  const [relatedDrugs, setRelatedDrugs] = useState<DrugCandidate[]>([])
  const [graphExpansion, setGraphExpansion] = useState<{targets: number, pathways: number, enzymes: number} | null>(null)
  const [selectedDrugs, setSelectedDrugs] = useState<DrugCandidate[]>([])
  const [llmText, setLlmText] = useState('')
  const [safetyText, setSafetyText] = useState('')
  const [interactions, setInteractions] = useState<Interaction[]>([])
  const [hyperedgeAlerts, setHyperedgeAlerts] = useState<HyperedgeAlert[]>([])
  const [expandedPrompts, setExpandedPrompts] = useState<Set<string>>(new Set())
  const [prompts, setPrompts] = useState<Record<string, string>>({})
  const abortRef = useRef<AbortController | null>(null)

  const togglePrompt = (key: string) => {
    setExpandedPrompts(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const analyze = async () => {
    if (!symptoms.trim()) return

    // Reset state
    setCandidates([])
    setRelatedDrugs([])
    setGraphExpansion(null)
    setSelectedDrugs([])
    setLlmText('')
    setSafetyText('')
    setInteractions([])
    setHyperedgeAlerts([])
    setPrompts({})
    setPhase('searching')

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    try {
      const resp = await fetch('/api/symptom/analyze/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symptoms,
          ...(age ? { age: parseInt(age) } : {}),
          ...(gender ? { gender } : {}),
          ...(weight ? { weight: parseFloat(weight) } : {}),
        }),
        signal: controller.signal,
      })

      const reader = resp.body?.getReader()
      if (!reader) return
      const decoder = new TextDecoder()
      let buffer = ''
      let currentPhase: Phase = 'searching'

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const evt = JSON.parse(line.slice(6))

            if (evt.type === 'phase') {
              currentPhase = evt.phase
              setPhase(evt.phase)
            } else if (evt.type === 'candidates') {
              setCandidates(evt.drugs)
            } else if (evt.type === 'graph_expansion') {
              setRelatedDrugs(evt.related_drugs || [])
              setGraphExpansion({ targets: evt.targets, pathways: evt.pathways, enzymes: evt.enzymes })
            } else if (evt.type === 'prompt') {
              setPrompts(prev => ({ ...prev, [currentPhase]: evt.text }))
            } else if (evt.type === 'token') {
              if (currentPhase === 'llm_matching') {
                setLlmText(prev => prev + evt.text)
              } else if (currentPhase === 'safety_conclusion') {
                setSafetyText(prev => prev + evt.text)
              }
            } else if (evt.type === 'selected') {
              setSelectedDrugs(evt.drugs)
            } else if (evt.type === 'interactions') {
              setInteractions(evt.interactions)
            } else if (evt.type === 'hyperedge_alerts') {
              setHyperedgeAlerts(evt.alerts)
            } else if (evt.type === 'done') {
              setPhase('done')
            }
          } catch { /* skip malformed */ }
        }
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        console.error('Stream error:', e)
        setPhase('done')
      }
    }
  }

  const isRunning = phase !== 'idle' && phase !== 'done'

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
          <Search size={24} className="text-blue-600" />
          Symptom Checker
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Describe symptoms to find matching drugs, then check if they can be safely combined.
        </p>
      </div>

      {/* Input */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
        <label className="block text-sm font-medium text-slate-700 mb-2">Patient Symptoms</label>
        <textarea
          value={symptoms}
          onChange={e => setSymptoms(e.target.value)}
          placeholder="e.g. high blood pressure, chest pain, blood clot risk, diabetes..."
          className="w-full h-24 p-3 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
          disabled={isRunning}
        />

        {/* Patient Demographics */}
        <div className="mt-3 pt-3 border-t border-slate-100">
          <div className="flex items-center gap-2 mb-2">
            <User size={14} className="text-slate-500" />
            <span className="text-xs font-medium text-slate-600">Patient Demographics (optional)</span>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs text-slate-500 mb-1">Age</label>
              <input
                type="number"
                value={age}
                onChange={e => setAge(e.target.value)}
                placeholder="e.g. 45"
                min="0"
                max="150"
                className="w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                disabled={isRunning}
              />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">Gender</label>
              <select
                value={gender}
                onChange={e => setGender(e.target.value)}
                className="w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white"
                disabled={isRunning}
              >
                <option value="">—</option>
                <option value="male">Male</option>
                <option value="female">Female</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">Weight (kg)</label>
              <input
                type="number"
                value={weight}
                onChange={e => setWeight(e.target.value)}
                placeholder="e.g. 70"
                min="0"
                max="500"
                step="0.1"
                className="w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                disabled={isRunning}
              />
            </div>
          </div>
        </div>
        <div className="flex items-center justify-between mt-3">
          <span className="text-xs text-slate-400">
            GraphRAG: semantic embeddings + hypergraph traversal + LLM reasoning + DDI safety
          </span>
          <button
            onClick={analyze}
            disabled={isRunning || !symptoms.trim()}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {isRunning && <Loader2 size={14} className="animate-spin" />}
            {isRunning ? 'Analyzing...' : 'Analyze'}
          </button>
        </div>
      </div>

      {/* Phase 1: Candidates */}
      {candidates.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-4 py-3 bg-blue-50 border-b border-blue-200 flex items-center gap-2">
            <Pill size={16} className="text-blue-600" />
            <span className="text-sm font-semibold text-blue-800">
              Seed Drugs ({candidates.length} by semantic similarity)
            </span>
          </div>
          <div className="p-4 max-h-60 overflow-y-auto">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {candidates.map(d => (
                <div
                  key={d.id}
                  className={`p-2 rounded-lg border text-xs ${
                    selectedDrugs.some(s => s.id === d.id)
                      ? 'bg-blue-50 border-blue-300'
                      : 'bg-slate-50 border-slate-200'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-semibold text-slate-800">{d.name}</span>
                    <div className="flex items-center gap-2">
                      {d.similarity != null && (
                        <span className="text-blue-600 font-mono text-[10px]">sim={d.similarity}</span>
                      )}
                      <span className="font-mono text-slate-400">{d.id}</span>
                    </div>
                  </div>
                  <p className="text-slate-600 line-clamp-2">{d.indication}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Graph Expansion Results */}
      {(relatedDrugs.length > 0 || graphExpansion) && (
        <div className="bg-white rounded-xl border border-purple-200 shadow-sm overflow-hidden">
          <div className="px-4 py-3 bg-purple-50 border-b border-purple-200 flex items-center gap-2">
            <Network size={16} className="text-purple-600" />
            <span className="text-sm font-semibold text-purple-800">
              Graph-Discovered Drugs ({relatedDrugs.length} via hypergraph traversal)
            </span>
          </div>
          {graphExpansion && (
            <div className="px-4 py-2 bg-purple-50/50 border-b border-purple-100 flex items-center gap-4 text-xs text-purple-700">
              <span>Shared targets: <b>{graphExpansion.targets}</b></span>
              <span>Shared pathways: <b>{graphExpansion.pathways}</b></span>
              <span>Shared enzymes: <b>{graphExpansion.enzymes}</b></span>
            </div>
          )}
          <div className="p-4 max-h-60 overflow-y-auto">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {relatedDrugs.map(d => (
                <div
                  key={d.id}
                  className={`p-2 rounded-lg border text-xs ${
                    selectedDrugs.some(s => s.id === d.id)
                      ? 'bg-purple-50 border-purple-300'
                      : 'bg-slate-50 border-slate-200'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-semibold text-slate-800">{d.name}</span>
                    <div className="flex items-center gap-2">
                      {d.graph_score != null && (
                        <span className="text-purple-600 font-mono text-[10px]">graph={d.graph_score}</span>
                      )}
                      <span className="font-mono text-slate-400">{d.id}</span>
                    </div>
                  </div>
                  {d.reasons && d.reasons.length > 0 && (
                    <div className="mt-1 space-y-0.5">
                      {d.reasons.slice(0, 2).map((r, i) => (
                        <p key={i} className="text-purple-700 text-[10px]">→ {r}</p>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Phase 2: LLM Drug Selection */}
      {(llmText || phase === 'llm_matching') && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-4 py-3 bg-indigo-50 border-b border-indigo-200 flex items-center gap-2">
            <Search size={16} className="text-indigo-600" />
            <span className="text-sm font-semibold text-indigo-800">LLM Drug Selection</span>
            {phase === 'llm_matching' && <Loader2 size={14} className="animate-spin text-indigo-600 ml-auto" />}
          </div>
          {prompts['llm_matching'] && (
            <div className="border-b border-slate-100">
              <button
                onClick={() => togglePrompt('llm_matching')}
                className="flex items-center gap-1 px-4 py-1.5 text-xs text-slate-500 hover:text-slate-700 w-full text-left"
              >
                {expandedPrompts.has('llm_matching') ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                <Code2 size={12} />
                LLM Prompt
              </button>
              {expandedPrompts.has('llm_matching') && (
                <pre className="mx-4 mb-2 p-3 bg-slate-900 text-slate-300 rounded-lg text-xs overflow-x-auto max-h-48 whitespace-pre-wrap">
                  {prompts['llm_matching']}
                </pre>
              )}
            </div>
          )}
          <div className="p-4">
            <div className="prose prose-sm max-w-none text-slate-700"><ReactMarkdown>{llmText}</ReactMarkdown></div>
          </div>
        </div>
      )}

      {/* Selected Drugs Summary */}
      {selectedDrugs.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-slate-600">Selected:</span>
          {selectedDrugs.map(d => (
            <span key={d.id} className="px-2.5 py-1 bg-blue-100 text-blue-800 rounded-full text-xs font-medium">
              {d.name} ({d.id})
            </span>
          ))}
        </div>
      )}

      {/* Phase 3: DDI Interactions */}
      {(interactions.length > 0 || (phase === 'safety_check' || phase === 'safety_conclusion' || phase === 'done')) && selectedDrugs.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-4 py-3 bg-amber-50 border-b border-amber-200 flex items-center gap-2">
            <AlertTriangle size={16} className="text-amber-600" />
            <span className="text-sm font-semibold text-amber-800">
              Drug-Drug Interactions ({interactions.length} found)
            </span>
          </div>
          <div className="p-4">
            {interactions.length === 0 ? (
              <p className="text-sm text-green-700">No direct interactions found between selected drugs.</p>
            ) : (
              <div className="space-y-2">
                {interactions.map((i, idx) => (
                  <div key={idx} className={`p-3 rounded-lg border ${severityColor[i.severity] || severityColor.unknown}`}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-semibold text-sm">{i.name_a} + {i.name_b}</span>
                      <span className="text-xs font-medium uppercase px-2 py-0.5 rounded-full border">
                        {i.severity}
                      </span>
                    </div>
                    <p className="text-xs opacity-80">{i.description}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Hyperedge Alerts */}
      {hyperedgeAlerts.length > 0 && (
        <div className="bg-white rounded-xl border border-red-200 shadow-sm overflow-hidden">
          <div className="px-4 py-3 bg-red-50 border-b border-red-200 flex items-center gap-2">
            <AlertTriangle size={16} className="text-red-600" />
            <span className="text-sm font-semibold text-red-800">
              Polypharmacy Alerts ({hyperedgeAlerts.length})
            </span>
          </div>
          <div className="p-4 space-y-2">
            {hyperedgeAlerts.map(a => (
              <div key={a.id} className="p-3 bg-red-50 rounded-lg border border-red-200 text-sm">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-semibold text-red-800">{a.label.replace(/_/g, ' ')}</span>
                  <span className="text-xs text-red-600">severity: {a.severity}</span>
                </div>
                <p className="text-xs text-red-700">
                  Involves: {a.overlap.join(', ')}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Phase 5: Safety Conclusion */}
      {(safetyText || phase === 'safety_conclusion') && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-4 py-3 bg-green-50 border-b border-green-200 flex items-center gap-2">
            <ShieldCheck size={16} className="text-green-600" />
            <span className="text-sm font-semibold text-green-800">Safety Assessment</span>
            {phase === 'safety_conclusion' && <Loader2 size={14} className="animate-spin text-green-600 ml-auto" />}
          </div>
          {prompts['safety_conclusion'] && (
            <div className="border-b border-slate-100">
              <button
                onClick={() => togglePrompt('safety_conclusion')}
                className="flex items-center gap-1 px-4 py-1.5 text-xs text-slate-500 hover:text-slate-700 w-full text-left"
              >
                {expandedPrompts.has('safety_conclusion') ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                <Code2 size={12} />
                LLM Prompt
              </button>
              {expandedPrompts.has('safety_conclusion') && (
                <pre className="mx-4 mb-2 p-3 bg-slate-900 text-slate-300 rounded-lg text-xs overflow-x-auto max-h-48 whitespace-pre-wrap">
                  {prompts['safety_conclusion']}
                </pre>
              )}
            </div>
          )}
          <div className="p-4">
            <div className="prose prose-sm max-w-none text-slate-700"><ReactMarkdown>{safetyText}</ReactMarkdown></div>
          </div>
        </div>
      )}
    </div>
  )
}
