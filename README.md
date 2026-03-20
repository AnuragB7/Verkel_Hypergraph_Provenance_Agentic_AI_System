# VHP: Verkle-Verified Hypergraph Provenance

**Trustworthy AI Decision Systems with Cryptographic Verification**

## Architecture

VHP implements a 3-layer verification stack:

| Layer | Component | Purpose |
|-------|-----------|---------|
| 1 | **Hypergraph** | Multi-way knowledge representation (entities, pairwise edges, hyperedges) |
| 2 | **Verkle Tree** | Constant-size (~96 byte) cryptographic proofs for data integrity |
| 3 | **Provenance DAG** | Hash-linked causal reasoning chain for auditability |

A pluggable **Reasoning Engine** sits on top (simulated rule-based or Ollama SLM).

## Project Structure

```
VHP/
├── backend/
│   ├── src/
│   │   ├── vhp/               # Core VHP library
│   │   │   ├── hypergraph.py   # Layer 1: Hypergraph KR
│   │   │   ├── verkle.py       # Layer 2: Verkle tree
│   │   │   ├── provenance.py   # Layer 3: Provenance DAG
│   │   │   ├── reasoning.py    # Pluggable reasoning engine
│   │   │   ├── audit.py        # Unified audit protocol
│   │   │   ├── pipeline.py     # VHP pipeline (ties all layers)
│   │   │   ├── crypto.py       # Cryptographic primitives
│   │   │   └── serialization.py
│   │   └── api/                # FastAPI application
│   │       ├── main.py
│   │       ├── dependencies.py
│   │       └── routers/
│   ├── data/                   # Data loaders + sample data
│   ├── tests/                  # pytest test suite
│   ├── requirements.txt
│   └── pyproject.toml
├── frontend/                   # React + TypeScript dashboard
│   ├── src/
│   │   ├── App.tsx
│   │   ├── api/client.ts
│   │   └── pages/
│   │       ├── Dashboard.tsx
│   │       ├── Hypergraph.tsx
│   │       ├── Verkle.tsx
│   │       ├── Provenance.tsx
│   │       ├── Reasoning.tsx
│   │       └── Benchmarks.tsx
│   └── package.json
└── paper/                      # LaTeX source
```

## Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt

# Run tests
PYTHONPATH=src:data pytest tests/ -v

# Start API server
PYTHONPATH=src:data uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev    # http://localhost:3000
```

### API Endpoints

| Group | Endpoint | Description |
|-------|----------|-------------|
| Health | `GET /api/health` | System status |
| Hypergraph | `GET /api/hypergraph/stats` | Graph statistics |
| Hypergraph | `GET /api/hypergraph/entities` | List entities |
| Hypergraph | `GET /api/hypergraph/hyperedges` | List hyperedges |
| Verkle | `GET /api/verkle/root` | Root commitment |
| Verkle | `POST /api/verkle/verify` | Verify partition |
| Verkle | `POST /api/verkle/tamper-detect` | Tamper detection demo |
| Reasoning | `POST /api/reasoning/query` | Process query through VHP |
| Reasoning | `GET /api/reasoning/scenarios` | Demo scenarios |
| Audit | `GET /api/audit/records` | List audit records |
| Audit | `GET /api/audit/records/{i}/verify` | Verify audit record |
| Benchmark | `POST /api/benchmark/performance` | Performance timing |
| Benchmark | `POST /api/benchmark/proof-sizes` | Verkle vs Merkle |
| Benchmark | `POST /api/benchmark/adversarial` | Adversarial tests |

## Key Innovation

Traditional knowledge graphs use **pairwise edges** (Drug A ↔ Drug B).
VHP uses **hyperedges** that connect 3+ entities simultaneously:

```
Hyperedge: {Warfarin, Aspirin, CKD_Stage_3} → polypharmacy_bleeding_renal (severity: 0.95)
```

This captures emergent risks that only arise when multiple factors co-occur —
the pairwise Warfarin↔Aspirin interaction alone rates "high", but with CKD
it escalates to "critical".

Every knowledge query generates a **Verkle proof** (constant 96 bytes) and
every reasoning step is recorded in a **Provenance DAG** with cryptographic
hash links, making the entire decision chain tamper-evident and auditable.

## Author

Anurag Rajkumar Bombarde — T-Systems International
