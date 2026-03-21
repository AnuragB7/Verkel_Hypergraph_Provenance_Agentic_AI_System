#!/usr/bin/env python3
"""VHP Paper Benchmark Runner.

Calls all benchmark API endpoints on the running VHP backend (localhost:8000)
and produces:
  1. Pretty terminal output with tables
  2. LaTeX table fragments for direct insertion into the paper
  3. A JSON dump of all raw results

Usage:
    python run_benchmarks.py              # run all benchmarks
    python run_benchmarks.py --only scale-extended,model-agnosticism
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
import time
from pathlib import Path

import httpx  # type: ignore[import-untyped]

BASE = "http://localhost:8000/api/benchmark"
TIMEOUT = 900.0  # LLM-heavy benchmarks can take several minutes


def post(endpoint: str) -> dict:
    url = f"{BASE}/{endpoint}"
    print(f"  → POST {url} ...", end=" ", flush=True)
    t0 = time.perf_counter()
    resp = httpx.post(url, timeout=TIMEOUT)
    elapsed = time.perf_counter() - t0
    resp.raise_for_status()
    print(f"done ({elapsed:.1f}s)")
    return resp.json()


# ── Table formatters ─────────────────────────────────────────────────

def _hline(widths):
    return "+" + "+".join("-" * (w + 2) for w in widths) + "+"


def _row(cells, widths):
    return "| " + " | ".join(str(c).ljust(w) for c, w in zip(cells, widths)) + " |"


def ascii_table(headers, rows, title=""):
    cols = list(zip(*([headers] + rows)))
    widths = [max(len(str(v)) for v in col) for col in cols]
    lines = []
    if title:
        lines.append(f"\n{'=' * 60}")
        lines.append(f"  {title}")
        lines.append(f"{'=' * 60}")
    lines.append(_hline(widths))
    lines.append(_row(headers, widths))
    lines.append(_hline(widths))
    for row in rows:
        lines.append(_row(row, widths))
    lines.append(_hline(widths))
    return "\n".join(lines)


def latex_table(headers, rows, caption, label, col_fmt=None):
    n = len(headers)
    if col_fmt is None:
        col_fmt = "@{}l" + "c" * (n - 1) + "@{}"
    lines = [
        r"\begin{table}[H]",
        r"\centering",
        rf"\caption{{{caption}}}",
        rf"\label{{{label}}}",
        rf"\begin{{tabular}}{{{col_fmt}}}",
        r"\toprule",
        " & ".join(rf"\textbf{{{h}}}" for h in headers) + r" \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(" & ".join(str(v) for v in row) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


# ── Individual benchmark runners ─────────────────────────────────────

def bench_scale_extended(all_results):
    """Table: Verkle vs Merkle at scale (proof size + time)."""
    data = post("scale-extended")
    all_results["scale_extended"] = data

    headers = ["Subgroups (k)", "Verkle Proof", "Merkle Proof", "Reduction",
               "V-Gen (ms)", "M-Gen (ms)", "V-Verify (ms)"]
    rows = []
    for r in data["results"]:
        rows.append([
            f"{r['leaves']:,}",
            f"{r['verkle_proof_bytes']} bytes",
            f"{r['merkle_proof_bytes']} bytes",
            f"{r['size_reduction_pct']}\\%",
            f"{r['verkle_proof_ms']:.4f}",
            f"{r['merkle_proof_ms']:.4f}",
            f"{r['verkle_verify_ms']:.4f}",
        ])
    print(ascii_table(headers, rows, "BENCHMARK: Verkle vs Merkle at Scale"))
    return latex_table(
        headers, rows,
        "Verkle vs Merkle proof size and generation time at varying knowledge base scale",
        "tab:scale_extended",
        col_fmt="@{}rcccccc@{}",
    )


def bench_build_time(all_results):
    """Table: Build + proof + verify time comparison."""
    data = post("build-time-comparison")
    all_results["build_time"] = data

    headers = ["Leaves", "V-Build (ms)", "M-Build (ms)",
               "V-Proof (ms)", "M-Proof (ms)", "V-Verify (ms)", "M-Verify (ms)"]
    rows = []
    for r in data["results"]:
        rows.append([
            str(r["leaves"]),
            f"{r['verkle_build_ms']:.4f}",
            f"{r['merkle_build_ms']:.4f}",
            f"{r['verkle_proof_ms']:.4f}",
            f"{r['merkle_proof_ms']:.4f}",
            f"{r['verkle_verify_ms']:.4f}",
            f"{r['merkle_verify_ms']:.4f}",
        ])
    print(ascii_table(headers, rows, "BENCHMARK: Verkle vs Merkle Build+Proof+Verify"))
    return latex_table(
        headers, rows,
        "Verkle vs Merkle tree construction and proof time comparison",
        "tab:build_time",
        col_fmt="@{}rcccccc@{}",
    )


def bench_layer_overhead(all_results):
    """Table: Per-layer overhead breakdown."""
    data = post("layer-overhead")
    all_results["layer_overhead"] = data

    headers = ["Layer", "Time (ms)", "% of Total"]
    total = data["total_ms"]
    rows = []
    for l in data["layers"]:
        pct = round(l["ms"] / total * 100, 1) if total > 0 else 0
        rows.append([l["layer"], f"{l['ms']:.4f}", f"{pct}\\%"])
    rows.append([r"\textbf{Total}", f"\\textbf{{{total:.4f}}}", r"\textbf{100\%}"])
    print(ascii_table(
        ["Layer", "Time (ms)", "% of Total"],
        [(l["layer"], f"{l['ms']:.4f}", f"{round(l['ms']/total*100,1)}%") for l in data["layers"]]
        + [("TOTAL", f"{total:.4f}", "100%")],
        "BENCHMARK: Per-Layer Overhead Breakdown",
    ))
    return latex_table(
        headers, rows,
        "VHP per-layer overhead breakdown for a single query",
        "tab:layer_overhead",
        col_fmt="@{}lcc@{}",
    )


def bench_dag_complexity(all_results):
    """Table: DAG depth/nodes vs query complexity."""
    data = post("dag-complexity")
    all_results["dag_complexity"] = data

    headers = ["Entities", "DAG Nodes", "DAG Depth", "Verkle Proofs", "Query (ms)"]
    rows = []
    for r in data["results"]:
        rows.append([
            str(r["entities"]),
            str(r["dag_nodes"]),
            str(r["dag_depth"]),
            str(r["verkle_proofs"]),
            f"{r['query_ms']:.2f}",
        ])
    print(ascii_table(headers, rows, "BENCHMARK: Provenance DAG Complexity vs Query Size"))
    return latex_table(
        headers, rows,
        "Provenance DAG depth and node count scaling with query complexity",
        "tab:dag_complexity",
        col_fmt="@{}rcccc@{}",
    )


def bench_hypergraph_vs_pairwise(all_results):
    """Table: Hypergraph vs pairwise risk detection."""
    data = post("hypergraph-vs-pairwise")
    all_results["hypergraph_vs_pairwise"] = data

    headers = ["Scenario", "Entities", "Pairwise Edges", "Hyperedges",
               "PW Detect", "HG Detect"]
    rows = []
    for c in data["comparisons"]:
        rows.append([
            c["scenario"][:40],
            str(c["entity_count"]),
            str(c["pairwise_edges_found"]),
            str(c["hyperedges_found"]),
            "Yes" if c["pairwise_detects_risk"] else "No",
            "Yes" if c["hypergraph_detects_risk"] else "No",
        ])
    s = data["summary"]
    print(ascii_table(headers, rows, "BENCHMARK: Hypergraph vs Pairwise Detection"))
    print(f"  Summary: Pairwise detection rate: {s['pairwise_detection_rate']}%, "
          f"Hypergraph detection rate: {s['hypergraph_detection_rate']}%")

    latex_headers = ["Entities", "Pairwise Edges", "Hyperedges", "PW Detects?", "HG Detects?"]
    latex_rows = []
    for c in data["comparisons"]:
        latex_rows.append([
            str(c["entity_count"]),
            str(c["pairwise_edges_found"]),
            str(c["hyperedges_found"]),
            r"\checkmark" if c["pairwise_detects_risk"] else "---",
            r"\checkmark" if c["hypergraph_detects_risk"] else "---",
        ])
    return latex_table(
        latex_headers, latex_rows,
        f"Hypergraph vs pairwise risk detection (PW: {s['pairwise_detection_rate']}\\%, HG: {s['hypergraph_detection_rate']}\\%)",
        "tab:hg_vs_pw",
        col_fmt="@{}rcccc@{}",
    )


def bench_model_agnosticism(all_results):
    """Table: VHP overhead identical across reasoning engines."""
    data = post("model-agnosticism")
    all_results["model_agnosticism"] = data

    headers = ["Reasoning Engine", "Proof Gen", "Proof Verify", "DAG Verify",
               "Audit Seal", "Audit Verify", "Total VHP"]
    rows = []
    for r in data["results"]:
        rows.append([
            r["model"],
            f"{r['verkle_proof_gen_ms']:.3f}",
            f"{r['verkle_verify_ms']:.3f}",
            f"{r['dag_verify_ms']:.3f}",
            f"{r['audit_seal_ms']:.3f}",
            f"{r['audit_verify_ms']:.3f}",
            f"{r['total_vhp_overhead_ms']:.3f}",
        ])
    print(ascii_table(headers, rows, "BENCHMARK: Model-Agnosticism (VHP Overhead by Engine)"))

    latex_headers = ["Reasoning Engine", "Proof Gen (ms)", "Verify (ms)",
                     "DAG (ms)", "Seal (ms)", "Total VHP (ms)"]
    latex_rows = []
    for r in data["results"]:
        latex_rows.append([
            r["model"],
            f"{r['verkle_proof_gen_ms']:.3f}",
            f"{r['verkle_verify_ms']:.3f}",
            f"{r['dag_verify_ms']:.3f}",
            f"{r['audit_seal_ms']:.3f}",
            f"{r['total_vhp_overhead_ms']:.3f}",
        ])
    return latex_table(
        latex_headers, latex_rows,
        "VHP verification overhead is constant regardless of reasoning engine (all times in ms)",
        "tab:model_agnosticism",
        col_fmt="@{}lccccc@{}",
    )


def bench_audit_storage(all_results):
    """Table: Audit record size at varying complexity."""
    data = post("audit-storage")
    all_results["audit_storage"] = data

    headers = ["Entities", "DAG Nodes", "Depth", "Proofs", "Record Size"]
    rows = []
    for r in data["results"]:
        rows.append([
            str(r["entities"]),
            str(r["dag_nodes"]),
            str(r["dag_depth"]),
            str(r["verkle_proofs"]),
            f"{r['record_kb']:.1f} KB",
        ])
    print(ascii_table(headers, rows, "BENCHMARK: Audit Record Storage Overhead"))
    return latex_table(
        headers, rows,
        "Audit record storage overhead at varying query complexity",
        "tab:audit_storage",
        col_fmt="@{}rcccc@{}",
    )


def bench_verification_throughput(all_results):
    """Table: Records verified per second."""
    data = post("verification-throughput")
    all_results["verification_throughput"] = data

    print(f"\n{'=' * 60}")
    print("  BENCHMARK: Verification Throughput")
    print(f"{'=' * 60}")
    print(f"  Records verified:  {data['records_verified']}")
    print(f"  All passed:        {data['passed']}/{data['records_verified']}")
    print(f"  Total time:        {data['total_seconds']:.4f}s")
    print(f"  Records/second:    {data['records_per_second']}")
    print(f"  Avg verify time:   {data['avg_verify_ms']:.4f} ms")

    headers = ["Metric", "Value"]
    rows = [
        ["Records verified", str(data["records_verified"])],
        ["All passed", f"{data['passed']}/{data['records_verified']}"],
        ["Total time", f"{data['total_seconds']:.3f}s"],
        ["Records/second", str(data["records_per_second"])],
        ["Avg verify time", f"{data['avg_verify_ms']:.3f} ms"],
    ]
    return latex_table(
        headers, rows,
        "Independent audit verification throughput (batch of 50 records)",
        "tab:verification_throughput",
        col_fmt="@{}lc@{}",
    )


def bench_incremental_update(all_results):
    """Table: Incremental update cost."""
    data = post("incremental-update")
    all_results["incremental_update"] = data

    headers = ["Leaves", "Update Time (ms)", "Root Changed"]
    rows = []
    for r in data["results"]:
        note = f" ({r['note']})" if r.get("note") else ""
        rows.append([
            f"{r['leaves']}{note}",
            f"{r['update_ms']:.4f}",
            "Yes" if r["root_changed"] else "No",
        ])
    print(ascii_table(headers, rows, "BENCHMARK: Incremental Update Cost"))
    return latex_table(
        headers, rows,
        "Cost of incrementally updating a single knowledge partition",
        "tab:incremental_update",
        col_fmt="@{}lcc@{}",
    )


def bench_performance(all_results):
    """Table: Core performance timings."""
    data = post("performance")
    all_results["performance"] = data

    headers = ["Operation", "Time (ms)"]
    rows = [[r["operation"], f"{r['ms']:.4f}"] for r in data["results"]]
    print(ascii_table(headers, rows, "BENCHMARK: Core Performance"))
    return latex_table(
        headers, rows,
        "Core VHP operation timings on DrugBank dataset",
        "tab:core_performance",
        col_fmt="@{}lc@{}",
    )


def bench_adversarial(all_results):
    """Table: Adversarial integrity tests."""
    data = post("adversarial")
    all_results["adversarial"] = data

    headers = ["Test", "Passed"]
    rows = [[t["test"], "PASS" if t["passed"] else "FAIL"] for t in data["tests"]]
    all_passed = data["all_passed"]
    print(ascii_table(headers, rows,
                      f"BENCHMARK: Adversarial Tests ({'ALL PASSED' if all_passed else 'FAILURES'})"))
    return latex_table(
        headers, rows,
        "Adversarial integrity test results",
        "tab:adversarial",
        col_fmt="@{}lc@{}",
    )


def bench_scalability(all_results):
    """Table: Scalability benchmark."""
    data = post("scalability")
    all_results["scalability"] = data

    headers = ["Leaves", "Build (ms)", "Proof Gen (ms)", "Verify (ms)"]
    rows = []
    for r in data["results"]:
        rows.append([
            str(r["leaves"]),
            f"{r['build_ms']:.4f}",
            f"{r['proof_gen_ms']:.4f}",
            f"{r['verify_ms']:.4f}",
        ])
    print(ascii_table(headers, rows, "BENCHMARK: Verkle Scalability"))
    return latex_table(
        headers, rows,
        "Verkle tree scalability: build, proof, and verification time vs leaf count",
        "tab:scalability",
        col_fmt="@{}rccc@{}",
    )


# ── Main ─────────────────────────────────────────────────────────────

ALL_BENCHMARKS = {
    "performance": bench_performance,
    "scalability": bench_scalability,
    "build-time-comparison": bench_build_time,
    "scale-extended": bench_scale_extended,
    "layer-overhead": bench_layer_overhead,
    "dag-complexity": bench_dag_complexity,
    "hypergraph-vs-pairwise": bench_hypergraph_vs_pairwise,
    "model-agnosticism": bench_model_agnosticism,
    "audit-storage": bench_audit_storage,
    "verification-throughput": bench_verification_throughput,
    "incremental-update": bench_incremental_update,
    "adversarial": bench_adversarial,
}


def main():
    parser = argparse.ArgumentParser(description="VHP paper benchmark runner")
    parser.add_argument("--only", type=str, default="",
                        help="Comma-separated list of benchmark names to run")
    parser.add_argument("--out", type=str, default="benchmark_results",
                        help="Output prefix for .json and .tex files")
    args = parser.parse_args()

    # Check server is up
    try:
        r = httpx.get("http://localhost:8000/api/health", timeout=5.0)
        r.raise_for_status()
        health = r.json()
        print(f"Server OK: {health.get('hypergraph', {}).get('entities', '?')} entities, "
              f"Verkle root: {health.get('verkle_root', '?')[:24]}...")
    except Exception as e:
        print(f"ERROR: Cannot reach backend at http://localhost:8000  ({e})")
        print("Start the backend first: cd backend && . .venv/bin/activate && python main.py")
        sys.exit(1)

    to_run = ALL_BENCHMARKS
    if args.only:
        names = [n.strip() for n in args.only.split(",")]
        to_run = {n: fn for n, fn in ALL_BENCHMARKS.items() if n in names}
        if not to_run:
            print(f"No matching benchmarks. Available: {', '.join(ALL_BENCHMARKS)}")
            sys.exit(1)

    all_results: dict = {}
    latex_tables: list[str] = []

    print(f"\nRunning {len(to_run)} benchmarks...\n")
    for name, fn in to_run.items():
        try:
            latex = fn(all_results)
            if latex:
                latex_tables.append(f"% === {name} ===\n{latex}")
        except Exception as e:
            print(f"  ✗ {name} FAILED: {e}")

    # Write outputs
    out_dir = Path(__file__).parent / "paper_benchmarks"
    out_dir.mkdir(exist_ok=True)

    json_path = out_dir / f"{args.out}.json"
    with open(json_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n✓ Raw JSON: {json_path}")

    tex_path = out_dir / f"{args.out}.tex"
    with open(tex_path, "w") as f:
        f.write("% Auto-generated VHP benchmark tables\n")
        f.write(f"% Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("\n\n".join(latex_tables))
    print(f"✓ LaTeX tables: {tex_path}")

    print(f"\n{'=' * 60}")
    print(f"  ALL BENCHMARKS COMPLETE ({len(all_results)} results)")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
