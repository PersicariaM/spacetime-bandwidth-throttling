"""
v2.0 High-Qubit Extension Experiment (N = 16, 24 [anchors] + 28..52)
Follow-up to Zenodo DOI: 10.5281/zenodo.24345478 (B_max >= 44.86 qubits)

Features:
1. Minimum-Error BFS Spanning Tree on native Heavy-Hex coupling map (0 SWAPs enforced)
2. GHZ Loschmidt Echo (Uncomputation) OR Direct GHZ mode (--mode echo|direct)
3. Symmetric CPMG [X, X] Dynamical Decoupling (Heron r2 native ISA safe)
4. Exact dt-aligned idle window (target ~500 ns, aligned to 16 dt granularity)
5. Automatic Backend Calibration Snapshot JSON for 1:1 Local MPS Digital Twin
6. Safe Dry-Run by default (consumes 0.00 RUs until --submit is explicitly passed)
"""

import argparse
import heapq
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit.library import XGate
from qiskit.transpiler import PassManager
from qiskit.transpiler.passes import ALAPScheduleAnalysis, PadDynamicalDecoupling
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler

# v1.0 overlap anchors (16, 24) + dense sweep around B_max = 44.86q
DEFAULT_QUBIT_GRID = [16, 24, 28, 32, 36, 40, 42, 44, 46, 48, 52]
IDLE_TARGET_NS = 500.0
DEFAULT_SHOTS = 8192
OUTPUT_DIR = Path("data/v2_experiments")


def get_two_qubit_gate_name(backend) -> str:
    """Detect native 2Q entangling gate (cz on Heron r2, fallback ecr/cx)."""
    ops = set(backend.target.operation_names)
    for gate in ("cz", "ecr", "cx"):
        if gate in ops:
            return gate
    raise RuntimeError(f"Unsupported native 2Q gate set on {backend.name}: {ops}")


def get_edge_error(backend, gate_name: str, u: int, v: int) -> float:
    """Safely extract 2Q gate error for undirected physical link (u, v)."""
    gate_props = backend.target[gate_name]
    for pair in ((u, v), (v, u)):
        prop = gate_props.get(pair)
        if prop is not None and prop.error is not None:
            return float(prop.error)
    return 0.05  # conservative penalty if calibration data missing


def get_readout_error(backend, q: int) -> float:
    """Safely extract single-qubit measurement error."""
    if "measure" in backend.target:
        prop = backend.target["measure"].get((q,))
        if prop is not None and prop.error is not None:
            return float(prop.error)
    return 0.03


def aligned_delay_dt(backend, target_ns: float, alignment: int = 16) -> tuple[int, float]:
    """Convert target_ns to hardware dt units aligned to pulse granularity."""
    dt_sec = backend.target.dt
    if dt_sec is None:
        raise RuntimeError(f"Backend {backend.name} does not expose target.dt")
    raw_dt = (target_ns * 1e-9) / dt_sec
    aligned_dt = max(alignment, int(round(raw_dt / alignment)) * alignment)
    actual_ns = aligned_dt * dt_sec * 1e9
    return aligned_dt, actual_ns


def select_best_ghz_tree(backend, n_qubits: int) -> dict:
    """
    Build a shallow, low-error BFS/Prim spanning tree of size n_qubits directly
    on the hardware coupling map so zero SWAP gates are required.
    """
    gate_name = get_two_qubit_gate_name(backend)
    adj = defaultdict(set)
    for u, v in backend.coupling_map.get_edges():
        adj[u].add(v)
        adj[v].add(u)

    all_qubits = sorted(adj.keys())
    # Prioritize candidate roots with lowest readout error and high connectivity
    candidate_roots = sorted(
        all_qubits,
        key=lambda q: (get_readout_error(backend, q), -len(adj[q])),
    )[:30]

    best_tree = None
    best_score = float("inf")

    for root in candidate_roots:
        visited = {root}
        nodes_order = [root]
        parent_edges = []
        depth_map = {root: 0}
        total_2q_err = 0.0

        # Priority queue favors: (shallow depth, low 2Q edge error)
        pq = []
        for nb in adj[root]:
            err = get_edge_error(backend, gate_name, root, nb)
            heapq.heappush(pq, (1, err, root, nb))

        while pq and len(nodes_order) < n_qubits:
            d, err, u, v = heapq.heappop(pq)
            if v in visited:
                continue
            visited.add(v)
            nodes_order.append(v)
            parent_edges.append((u, v))
            depth_map[v] = d
            total_2q_err += err
            for nb in adj[v]:
                if nb not in visited:
                    nb_err = get_edge_error(backend, gate_name, v, nb)
                    heapq.heappush(pq, (d + 1, nb_err, v, nb))

        if len(nodes_order) < n_qubits:
            continue

        max_depth = max(depth_map.values())
        root_ro_err = get_readout_error(backend, root)
        mean_ro_err = float(np.mean([get_readout_error(backend, q) for q in nodes_order]))

        # Composite SRE objective: keep tree shallow + minimize cumulative 2Q & root readout error
        score = (0.015 * max_depth) + total_2q_err + (2.0 * root_ro_err) + (0.5 * mean_ro_err)
        if score < best_score:
            best_score = score
            best_tree = {
                "root": root,
                "nodes_order": nodes_order,
                "parent_edges": parent_edges,
                "tree_depth": max_depth,
                "sum_2q_error": round(total_2q_err, 6),
                "mean_2q_error": round(total_2q_err / max(1, len(parent_edges)), 6),
                "root_readout_error": round(root_ro_err, 6),
                "mean_readout_error": round(mean_ro_err, 6),
            }

    if best_tree is None:
        raise RuntimeError(f"Could not find connected {n_qubits}-qubit subgraph on {backend.name}")
    return best_tree


def build_ghz_circuit(
    tree_info: dict,
    delay_dt: int,
    mode: str = "echo",
    name: str = "ghz",
) -> QuantumCircuit:
    """
    Build logical GHZ circuit mapped 1:1 to tree_info['nodes_order'].
    Logical qubit 0 corresponds to physical root qubit.
    """
    nodes = tree_info["nodes_order"]
    n_qubits = len(nodes)
    phys_to_log = {phys_q: idx for idx, phys_q in enumerate(nodes)}

    qc = QuantumCircuit(n_qubits, name=name)
    # 1. State Preparation (BFS Tree)
    qc.h(0)
    for u, v in tree_info["parent_edges"]:
        qc.cx(phys_to_log[u], phys_to_log[v])
    qc.barrier()

    # 2. Controlled Entangled Hold Window
    if delay_dt > 0:
        for q in range(n_qubits):
            qc.delay(delay_dt, q, unit="dt")
        qc.barrier()

    # 3. Optional Uncomputation (Loschmidt Echo) -> focuses N-qubit phase onto root q0
    if mode == "echo":
        for u, v in reversed(tree_info["parent_edges"]):
            qc.cx(phys_to_log[u], phys_to_log[v])
        qc.h(0)
        qc.barrier()

    qc.measure_all()
    return qc


def transpile_with_cpmg_dd(backend, qc: QuantumCircuit, initial_layout: list[int]) -> QuantumCircuit:
    """
    Transpile onto fixed hardware tree layout and apply symmetric CPMG [X, X] DD.
    Note: Heron r2 native ISA has no YGate, so [XGate(), XGate()] is mandatory.
    """
    pm = generate_preset_pass_manager(
        optimization_level=1,
        backend=backend,
        initial_layout=initial_layout,
    )
    isa_qc = pm.run(qc)

    swap_count = isa_qc.count_ops().get("swap", 0)
    if swap_count > 0:
        raise RuntimeError(
            f"Pre-flight guard triggered: {qc.name} introduced {swap_count} SWAP gates!"
        )

    dd_pm = PassManager(
        [
            ALAPScheduleAnalysis(target=backend.target),
            PadDynamicalDecoupling(
                target=backend.target,
                dd_sequence=[XGate(), XGate()],
            ),
        ]
    )
    return dd_pm.run(isa_qc)


def snapshot_backend_calibration(backend, active_qubits: set[int]) -> dict:
    """Save exact T1, T2, readout, and 2Q gate calibration for 1:1 MPS digital twin."""
    gate_name = get_two_qubit_gate_name(backend)
    qubit_cal = {}
    for q in sorted(active_qubits):
        qprops = backend.target.qubit_properties[q] if backend.target.qubit_properties else None
        qubit_cal[str(q)] = {
            "t1_sec": float(qprops.t1) if (qprops and qprops.t1 is not None) else None,
            "t2_sec": float(qprops.t2) if (qprops and qprops.t2 is not None) else None,
            "frequency_hz": float(qprops.frequency) if (qprops and qprops.frequency is not None) else None,
            "readout_error": get_readout_error(backend, q),
        }

    edge_cal = {}
    for u, v in backend.coupling_map.get_edges():
        if u in active_qubits and v in active_qubits and u < v:
            edge_cal[f"{u}-{v}"] = get_edge_error(backend, gate_name, u, v)

    return {
        "backend_name": backend.name,
        "native_2q_gate": gate_name,
        "dt_sec": backend.target.dt,
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "qubits": qubit_cal,
        "edges_2q_error": edge_cal,
    }


def main():
    parser = argparse.ArgumentParser(description="v2.0 High-Qubit GHZ Throttling Experiment")
    parser.add_argument("--backend", type=str, default="ibm_fez", help="Target QPU (e.g., ibm_fez, ibm_kingston, ibm_marrakesh)")
    parser.add_argument("--mode", type=str, choices=["echo", "direct"], default="echo", help="GHZ probe mode")
    parser.add_argument("--shots", type=int, default=DEFAULT_SHOTS, help="Shots per circuit (recommended >= 4096)")
    parser.add_argument("--idle-ns", type=float, default=IDLE_TARGET_NS, help="Target idle window in ns")
    parser.add_argument("--qubits", type=int, nargs="+", default=DEFAULT_QUBIT_GRID, help="Qubit counts to sweep")
    parser.add_argument("--submit", action="store_true", help="Actually submit job to IBM QPU (consumes RUs)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    print(f"[1/4] Connecting to IBM Quantum backend: {args.backend} ...")
    service = QiskitRuntimeService()
    backend = service.backend(args.backend)

    delay_dt, actual_idle_ns = aligned_delay_dt(backend, args.idle_ns, alignment=16)
    print(f"      dt = {backend.target.dt * 1e9:.2f} ns | target idle = {args.idle_ns:.1f} ns -> aligned = {delay_dt} dt ({actual_idle_ns:.1f} ns)")

    isa_circuits = []
    circuit_manifest = []
    all_active_qubits = set()

    print(f"[2/4] Building 0-SWAP BFS Trees & Transpiling ({len(args.qubits) * 2} circuits, mode={args.mode}) ...")
    print(f"{'N':>4} | {'TreeDepth':>9} | {'Sum2QErr':>9} | {'RootRO':>7} | {'2Q_Depth(0ns)':>13} | {'2Q_Depth(Hold)':>14}")
    print("-" * 72)

    for n in args.qubits:
        tree_info = select_best_ghz_tree(backend, n)
        all_active_qubits.update(tree_info["nodes_order"])

        qc_base = build_ghz_circuit(tree_info, delay_dt=0, mode=args.mode, name=f"ghz_{args.mode}_N{n}_0ns")
        qc_hold = build_ghz_circuit(tree_info, delay_dt=delay_dt, mode=args.mode, name=f"ghz_{args.mode}_N{n}_{int(round(actual_idle_ns))}ns")

        isa_base = transpile_with_cpmg_dd(backend, qc_base, tree_info["nodes_order"])
        isa_hold = transpile_with_cpmg_dd(backend, qc_hold, tree_info["nodes_order"])

        gate_2q = get_two_qubit_gate_name(backend)
        d2q_base = isa_base.depth(lambda inst: inst.operation.name == gate_2q)
        d2q_hold = isa_hold.depth(lambda inst: inst.operation.name == gate_2q)

        print(
            f"{n:>4} | {tree_info['tree_depth']:>9} | {tree_info['sum_2q_error']:>9.4f} | "
            f"{tree_info['root_readout_error']:>7.4f} | {d2q_base:>13} | {d2q_hold:>14}"
        )

        isa_circuits.extend([isa_base, isa_hold])
        circuit_manifest.append(
            {
                "n_qubits": n,
                "mode": args.mode,
                "tree_info": tree_info,
                "circuits": [
                    {"index": len(isa_circuits) - 2, "name": qc_base.name, "idle_ns": 0.0, "depth_2q": d2q_base},
                    {"index": len(isa_circuits) - 1, "name": qc_hold.name, "idle_ns": actual_idle_ns, "depth_2q": d2q_hold},
                ],
            }
        )

    print("[3/4] Capturing live Backend Calibration Snapshot for Local MPS Digital Twin ...")
    cal_snapshot = snapshot_backend_calibration(backend, all_active_qubits)

    metadata = {
        "experiment_version": "v2.0_high_qubit_extension",
        "parent_doi": "10.5281/zenodo.24345478",
        "backend": args.backend,
        "mode": args.mode,
        "shots": args.shots,
        "idle_target_ns": args.idle_ns,
        "idle_actual_ns": actual_idle_ns,
        "idle_delay_dt": delay_dt,
        "qubit_grid": args.qubits,
        "manifest": circuit_manifest,
        "calibration_snapshot": cal_snapshot,
        "job_id": None,
        "submitted": False,
    }

    meta_path = OUTPUT_DIR / f"v2_manifest_{args.backend}_{args.mode}_{ts}.json"

    if not args.submit:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
        print(f"\n[DRY-RUN COMPLETE] 0.00 RUs consumed. All {len(isa_circuits)} circuits passed 0-SWAP guard.")
        print(f"Manifest & Calibration Snapshot saved -> {meta_path}")
        print(f"To submit to QPU, re-run with: --submit")
        return

    print(f"[4/4] Submitting {len(isa_circuits)} circuits ({args.shots} shots each) to {args.backend} ...")
    sampler = Sampler(mode=backend)
    # Disable auto-DD so only our symmetric CPMG [X, X] schedule applies
    sampler.options.dynamical_decoupling.enable = False
    sampler.options.environment.job_tags = ["GHZ_State_Benchmark", "v2_high_qubit", args.mode]

    job = sampler.run(isa_circuits, shots=args.shots)
    job_id = job.job_id()
    metadata["job_id"] = job_id
    metadata["submitted"] = True

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"\n[SUBMITTED] Job ID: {job_id}")
    print(f"Manifest saved -> {meta_path}")
    print("Tip: Monitor queue status on IBM Quantum Platform or fetch results once DONE.")
    print("Note on bitstrings: Qiskit uses little-endian order, so root qubit q0 is bitstring[-1].")


if __name__ == "__main__":
    main()