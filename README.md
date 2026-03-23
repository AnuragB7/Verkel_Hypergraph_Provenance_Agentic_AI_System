# VHP: Verkle-Verified Hypergraph Provenance

[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-sa/4.0/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://react.dev/)

> **Trustworthy AI Decision Systems with Cryptographic Verification**

VHP is an open-source framework that combines **hypergraph knowledge representation**, **Verkle tree cryptographic proofs**, and **provenance-tracked reasoning** to build AI decision pipelines that are tamper-evident, auditable, and explainable. It is demonstrated on a pharmaceutical drug-interaction use case using DrugBank data.

---

## Table of Contents

- [Architecture](#architecture)
- [Key Innovation](#key-innovation)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [API Reference](#api-reference)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)
- [Citation](#citation)
- [Author](#author)

---

## Architecture

VHP implements a 3-layer verification stack:

| Layer | Component | Purpose |
|-------|-----------|---------|
| 1 | **Hypergraph** | Multi-way knowledge representation (entities, pairwise edges, hyperedges) |
| 2 | **Verkle Tree** | Constant-size (~96 byte) cryptographic proofs for data integrity |
| 3 | **Provenance DAG** | Hash-linked causal reasoning chain for auditability |

A pluggable **Reasoning Engine** sits on top (simulated rule-based or Ollama SLM).

---

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

---

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
└── LICENSE
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- npm or yarn

### Backend

```bash
cd backend
pip install -r requirements.txt

# Start API server
PYTHONPATH=src:data uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The dashboard will be available at `http://localhost:3000`.

---

## API Reference

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

Full interactive API documentation is available at `/docs` (Swagger UI) when the backend is running.

---

## Testing

```bash
cd backend
PYTHONPATH=src:data pytest tests/ -v
```

---

## Contributing

Contributions are welcome! Please follow these steps:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/my-feature`)
3. **Commit** your changes (`git commit -m 'Add my feature'`)
4. **Push** to the branch (`git push origin feature/my-feature`)
5. **Open** a Pull Request

Please make sure all existing tests pass before submitting a PR.

---

## License

This project is licensed under the [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License](LICENSE).

You are free to share and adapt this work for non-commercial purposes, as long as you give appropriate credit and distribute your contributions under the same license.

---

## Citation

If you use VHP in your research, please cite:

```bibtex
@misc{bombarde2026vhp,
  title   = {Verkle-Verified Hypergraph Provenance for Trustworthy AI Decision Systems},
  author  = {Bombarde, Anurag Rajkumar},
  year    = {2026},
  url     = {https://github.com/AnuragB7/Verkel_Hypergraph_Provenance_Agentic_AI_System}
}
```

---

## Author

**Anurag Rajkumar Bombarde** — T-Systems International
