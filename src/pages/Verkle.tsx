import { useQuery } from '@tanstack/react-query'
import { verkleApi, hypergraphApi } from '../api/client'
import { useState } from 'react'
import { Shield, CheckCircle, XCircle, AlertTriangle } from 'lucide-react'

export default function Verkle() {
  const root = useQuery({ queryKey: ['verkle-root'], queryFn: verkleApi.getRoot })
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

      {/* Root info */}
      {root.data && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 mb-6">
          <div className="flex items-center gap-3 mb-3">
            <Shield size={24} className="text-blue-600" />
            <h2 className="text-lg font-semibold text-slate-700">Root Commitment</h2>
          </div>
          <code className="text-xs bg-slate-100 p-2 rounded block break-all mb-2">{root.data.root}</code>
          <p className="text-sm text-slate-500">
            Depth: {root.data.depth} &middot; Leaves: {root.data.leaf_count}
          </p>
          <p className="text-xs text-slate-400 mt-1">
            Constant proof size: ~96 bytes regardless of tree size
          </p>
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
