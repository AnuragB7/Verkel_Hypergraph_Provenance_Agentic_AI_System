import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// ─── Health ──────────────────────────────────────────────────
export const healthApi = {
  check: () => api.get('/health').then(r => r.data),
}

// ─── Hypergraph (Layer 1) ────────────────────────────────────
export const hypergraphApi = {
  getStats: () => api.get('/hypergraph/stats').then(r => r.data),
  getEntities: (limit = 200, offset = 0) =>
    api.get('/hypergraph/entities', { params: { limit, offset } }).then(r => r.data),
  getEntity: (id: string) =>
    api.get(`/hypergraph/entities/${encodeURIComponent(id)}`).then(r => r.data),
  getEdges: (limit = 500, offset = 0) =>
    api.get('/hypergraph/edges', { params: { limit, offset } }).then(r => r.data),
  getHyperedges: () =>
    api.get('/hypergraph/hyperedges').then(r => r.data),
  getNeighbors: (id: string, relation?: string) =>
    api.get(`/hypergraph/neighbors/${encodeURIComponent(id)}`, { params: { relation } }).then(r => r.data),
  getPartitions: () =>
    api.get('/hypergraph/partitions').then(r => r.data),
  extractSubgraph: (entity_ids: string[], max_hops = 2) =>
    api.post('/hypergraph/subgraph', { entity_ids, max_hops }).then(r => r.data),
}

// ─── Verkle (Layer 2) ────────────────────────────────────────
export const verkleApi = {
  getRoot: () => api.get('/verkle/root').then(r => r.data),
  getProof: (partition: string) =>
    api.get(`/verkle/proof/${encodeURIComponent(partition)}`).then(r => r.data),
  verify: (partition_name: string) =>
    api.post('/verkle/verify', { partition_name }).then(r => r.data),
  getRootChain: () =>
    api.get('/verkle/root-chain').then(r => r.data),
  verifyRootChain: () =>
    api.get('/verkle/root-chain/verify').then(r => r.data),
  tamperDetect: (partition_name: string) =>
    api.post('/verkle/tamper-detect', { partition_name }).then(r => r.data),
}

// ─── Provenance (Layer 3) ────────────────────────────────────
export const provenanceApi = {
  listRecords: () =>
    api.get('/provenance/records').then(r => r.data),
  getDag: (index: number) =>
    api.get(`/provenance/records/${index}/dag`).then(r => r.data),
  getChain: (index: number, nodeId: string) =>
    api.get(`/provenance/records/${index}/chain/${nodeId}`).then(r => r.data),
}

// ─── Reasoning ───────────────────────────────────────────────
export const reasoningApi = {
  query: (query: string, entity_ids: string[]) =>
    api.post('/reasoning/query', { query, entity_ids }).then(r => r.data),
  getEngine: () =>
    api.get('/reasoning/engine').then(r => r.data),
  getScenarios: () =>
    api.get('/reasoning/scenarios').then(r => r.data),
  getModels: () =>
    api.get('/reasoning/models').then(r => r.data),
  switchModel: (model: string) =>
    api.post('/reasoning/engine/switch', { model }).then(r => r.data),
}

// ─── Audit ───────────────────────────────────────────────────
export const auditApi = {
  listRecords: () =>
    api.get('/audit/records').then(r => r.data),
  getRecord: (index: number) =>
    api.get(`/audit/records/${index}`).then(r => r.data),
  verifyRecord: (index: number) =>
    api.get(`/audit/records/${index}/verify`).then(r => r.data),
}

// ─── Benchmark ───────────────────────────────────────────────
export const benchmarkApi = {
  performance: () =>
    api.post('/benchmark/performance').then(r => r.data),
  proofSizes: () =>
    api.post('/benchmark/proof-sizes').then(r => r.data),
  adversarial: () =>
    api.post('/benchmark/adversarial').then(r => r.data),
  scalability: () =>
    api.post('/benchmark/scalability').then(r => r.data),
  layerOverhead: () =>
    api.post('/benchmark/layer-overhead').then(r => r.data),
  dagComplexity: () =>
    api.post('/benchmark/dag-complexity').then(r => r.data),
  hypergraphVsPairwise: () =>
    api.post('/benchmark/hypergraph-vs-pairwise').then(r => r.data),
  buildTimeComparison: () =>
    api.post('/benchmark/build-time-comparison').then(r => r.data),
}
