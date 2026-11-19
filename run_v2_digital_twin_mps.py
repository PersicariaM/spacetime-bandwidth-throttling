"""
v2.0 Local Digital Twin Simulator (MPS Engine) & QPU Result Fetcher
- Reads the exact calibration snapshot saved at QPU submission time
- Simulates 1:1 noise-matched GHZ Echo circuits (N = 16..52) using Qiskit Aer MPS
- Optionally fetches completed QPU job results and computes Residual = QPU_Diff - Twin_Diff
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from qiskit_aer.noise import (
    NoiseModel,
    ReadoutError,
    depolarizing_error,
    thermal_relaxation_error,
)

# Typical Heron r2 native gate durations
GATE_TIME_1Q_NS = 32.0
GATE_TIME_2Q_NS = 68.0
DEFAULT_T1_SEC = 200e-6
DEFAULT_T2_SEC = 150e-6


def build_snapshot_noise_model(
    cal_snapshot: dict,
    tree_nodes: list[int],
    parent_edges: list[list[int]],
    idle_ns: float,
) -> NoiseModel:
    """Construct a local Aer NoiseModel matching physical qubits, edges, and CPMG delay window."""
    noise_model = NoiseModel()
    q_cal = cal_snapshot["qubits"]
    e_cal = cal_snapshot["edges_2q_error"]

    phys_to_log = {phys_q: idx for idx, phys_q in enumerate(tree_nodes)}
    half_idle_sec = (idle_ns * 0.5) * 1e-9

    for phys_q, log_q in phys_to_log.items():
        info = q_cal.get(str(phys_q), {})
        t1 = info.get("t1_sec") or DEFAULT_T1_SEC
        t2 = info.get("t2_sec") or DEFAULT_T2_SEC
        t2 = min(t2, 2.0 * t1)
        ro_err = float(info.get("readout_error") or 0.01)

        # 1Q thermal relaxation during standard single-qubit gates
        err_1q = thermal_relaxation_error(t1, t2, GATE_TIME_1Q_NS * 1e-9)
        noise_model.add_quantum_error(err_1q, ["rz", "sx", "x"], [log_q])

        # Idle delay thermal relaxation (each half of the symmetric CPMG [X, X] window)
        if half_idle_sec > 0:
            err_delay = thermal_relaxation_error(t1, t2, half_idle_sec)
            noise_model.add_quantum_error(err_delay, ["delay"], [log_q])

        # Readout bit-flip error
        ro = ReadoutError([[1.0 - ro_err, ro_err], [ro_err, 1.0 - ro_err]])
        noise_model.add_readout_error(ro, [log_q])

    for u, v in parent_edges:
        lu, lv = phys_to_log[u], phys_to_log[v]
        key = f"{min(u, v)}-{max(u, v)}"
        edge_err = float(e_cal.get(key, 0.004))

        iu = q_cal.get(str(u), {})
        iv = q_cal.get(str(v), {})
        t1_u, t2_u = iu.get("t1_sec") or DEFAULT_T1_SEC, iu.get("t2_sec") or DEFAULT_T2_SEC
        t1_v, t2_v = iv.get("t1_sec") or DEFAULT_T1_SEC, iv.get("t2_sec") or DEFAULT_T2_SEC
        t2_u, t2_v = min(t2_u, 2.0 * t1_u), min(t2_v, 2.0 * t1_v)

        th_u = thermal_relaxation_error(t1_u, t2_u, GATE_TIME_2Q_NS * 1e-9)
        th_v = thermal_relaxation_error(t1_v, t2_v, GATE_TIME_2Q_NS * 1e-9)
        th_2q = th_u.expand(th_v)

        th_fidelity = float(np.real(np.trace(th_2q.to_quantumchannel().data)) / 16.0)
        th_infid = max(0.0, 1.0 - th_fidelity)
        rem_depol = max(0.0, min(0.5, (edge_err - th_infid) * (16.0 / 15.0)))

        total_2q_err = th_2q.compose(depolarizing_error(rem_depol, 2)) if rem_depol > 0 else th_2q
        noise_model.add_quantum_error(total_2q_err, ["cz"], [lu, lv])
        noise_model.add_quantum_error(total_2q_err, ["cz"], [lv, lu])

    return noise_model


def build_compact_twin_circuit(
    tree_info: dict,
    cal_snapshot: dict,
    idle_ns: float,
    mode: str = "echo",
) -> tuple[QuantumCircuit, NoiseModel]:
    """
    Build a pure-unitary + standard delay circuit transpiled to compact native gates
    ["rz", "sx", "x", "cz", "delay", "measure"] for fast Aer MPS simulation.
    """
    nodes = tree_info["nodes_order"]
    n_qubits = len(nodes)
    phys_to_log = {phys_q: idx for idx, phys_q in enumerate(nodes)}
    noise_model = build_snapshot_noise_model(cal_snapshot, nodes, tree_info["parent_edges"], idle_ns)

    qc = QuantumCircuit(n_qubits)
    # 1. GHZ Preparation
    qc.h(0)
    for u, v in tree_info["parent_edges"]:
        qc.cx(phys_to_log[u], phys_to_log[v])
    qc.barrier()

    # 2. Controlled Idle Window with symmetric CPMG [X, X] Dynamical Decoupling
    if idle_ns > 0:
        half_idle_ns = idle_ns * 0.5
        for log_q in range(n_qubits):
            qc.delay(half_idle_ns, log_q, unit="ns")
            qc.x(log_q)
            qc.delay(half_idle_ns, log_q, unit="ns")
            qc.x(log_q)
        qc.barrier()

    # 3. GHZ Uncomputation (Echo)
    if mode == "echo":
        for u, v in reversed(tree_info["parent_edges"]):
            qc.cx(phys_to_log[u], phys_to_log[v])
        qc.h(0)
        qc.barrier()

    qc.measure_all()
    compact_qc = transpile(qc, basis_gates=["rz", "sx", "x", "cz", "delay", "measure"], optimization_level=1)
    return compact_qc, noise_model


def compute_metrics_from_counts(counts: dict[str, int], n_qubits: int, mode: str) -> dict:
    """
    Extract both Root Echo Fidelity P(q0=0) and Full-String Fidelity P(0^N) / P(0^N)+P(1^N).
    Qiskit bitstrings are little-endian: qubit 0 is bitstring[-1].
    """
    total_shots = sum(counts.values())
    if total_shots == 0:
        raise ValueError("Empty counts dictionary")

    root_zero_shots = 0
    all_zero_shots = 0
    all_one_shots = 0
    hamming_sum = 0

    zero_str = "0" * n_qubits
    one_str = "1" * n_qubits

    for raw_bs, cnt in counts.items():
        bs = raw_bs.replace(" ", "")
        if bs[-1] == "0":
            root_zero_shots += cnt
        if bs == zero_str:
            all_zero_shots += cnt
        elif bs == one_str:
            all_one_shots += cnt
        hamming_sum += bs.count("1") * cnt

    p_root_0 = root_zero_shots / total_shots
    if mode == "echo":
        p_full = all_zero_shots / total_shots
    else:
        p_full = (all_zero_shots + all_one_shots) / total_shots

    mean_hamming = hamming_sum / (total_shots * n_qubits)
    return {
        "p_root_0": p_root_0,
        "err_root": 1.0 - p_root_0,
        "p_full": p_full,
        "err_full": 1.0 - p_full,
        "mean_bitflip_rate": mean_hamming,
    }


def run_mps_digital_twin(manifest: dict, twin_shots: int) -> pd.DataFrame:
    """Run 1:1 local MPS simulation for every circuit in the QPU manifest."""
    sim = AerSimulator(
        method="matrix_product_state",
        matrix_product_state_max_bond_dimension=32,
        max_parallel_threads=0,
    )

    cal_snapshot = manifest["calibration_snapshot"]
    mode = manifest["mode"]
    rows = []

    print(f"[MPS Twin] Simulating {len(manifest['manifest'])} qubit scales ({twin_shots} shots/circuit) ...")
    for entry in manifest["manifest"]:
        n = entry["n_qubits"]
        tree_info = entry["tree_info"]
        t0 = time.perf_counter()

        res_by_cond = {}
        for cinfo in entry["circuits"]:
            idle_ns = float(cinfo["idle_ns"])
            cond_key = "hold" if idle_ns > 0 else "base"
            qc_twin, noise_model = build_compact_twin_circuit(tree_info, cal_snapshot, idle_ns, mode=mode)
            job = sim.run(qc_twin, noise_model=noise_model, shots=twin_shots)
            counts = job.result().get_counts()
            res_by_cond[cond_key] = compute_metrics_from_counts(counts, n, mode)

        dt_sec = time.perf_counter() - t0
        twin_diff_root = res_by_cond["hold"]["err_root"] - res_by_cond["base"]["err_root"]
        twin_diff_full = res_by_cond["hold"]["err_full"] - res_by_cond["base"]["err_full"]

        print(
            f"  N={n:>2} | Twin P_root(0ns)={res_by_cond['base']['p_root_0']:.4f} -> "
            f"P_root(Hold)={res_by_cond['hold']['p_root_0']:.4f} | "
            f"Twin_Diff_Root={twin_diff_root:+.4f} | ({dt_sec:.1f}s)"
        )

        rows.append(
            {
                "n_qubits": n,
                "tree_depth": tree_info["tree_depth"],
                "sum_2q_error": tree_info["sum_2q_error"],
                "twin_p_root_0ns": res_by_cond["base"]["p_root_0"],
                "twin_p_root_hold": res_by_cond["hold"]["p_root_0"],
                "twin_diff_root": twin_diff_root,
                "twin_p_full_0ns": res_by_cond["base"]["p_full"],
                "twin_p_full_hold": res_by_cond["hold"]["p_full"],
                "twin_diff_full": twin_diff_full,
            }
        )

    return pd.DataFrame(rows)


def fetch_and_merge_qpu_results(manifest: dict, df_twin: pd.DataFrame) -> pd.DataFrame | None:
    """Fetch IBM Quantum job results if DONE and compute QPU vs Digital Twin Residuals."""
    job_id = manifest.get("job_id")
    if not job_id:
        print("[QPU Fetch] No job_id in manifest (Dry-Run file). Skipping QPU fetch.")
        return None

    from qiskit_ibm_runtime import QiskitRuntimeService

    service = QiskitRuntimeService()
    job = service.job(job_id)
    status = str(job.status())
    print(f"[QPU Fetch] Job {job_id} status = {status}")
    if "DONE" not in status.upper():
        print("            Job is not DONE yet. Digital Twin CSV is saved; re-run with --fetch-only later!")
        return None

    result = job.result()
    mode = manifest["mode"]
    qpu_rows = []

    for entry in manifest["manifest"]:
        n = entry["n_qubits"]
        cond_metrics = {}
        for cinfo in entry["circuits"]:
            idx = cinfo["index"]
            cond_key = "hold" if float(cinfo["idle_ns"]) > 0 else "base"
            pub_res = result[idx]
            counts = pub_res.data.meas.get_counts()
            cond_metrics[cond_key] = compute_metrics_from_counts(counts, n, mode)

        qpu_diff_root = cond_metrics["hold"]["err_root"] - cond_metrics["base"]["err_root"]
        qpu_diff_full = cond_metrics["hold"]["err_full"] - cond_metrics["base"]["err_full"]
        qpu_rows.append(
            {
                "n_qubits": n,
                "qpu_p_root_0ns": cond_metrics["base"]["p_root_0"],
                "qpu_p_root_hold": cond_metrics["hold"]["p_root_0"],
                "qpu_diff_root": qpu_diff_root,
                "qpu_p_full_0ns": cond_metrics["base"]["p_full"],
                "qpu_p_full_hold": cond_metrics["hold"]["p_full"],
                "qpu_diff_full": qpu_diff_full,
                "qpu_bitflip_0ns": cond_metrics["base"]["mean_bitflip_rate"],
                "qpu_bitflip_hold": cond_metrics["hold"]["mean_bitflip_rate"],
            }
        )

    df_qpu = pd.DataFrame(qpu_rows)
    df_merged = pd.merge(df_twin, df_qpu, on="n_qubits")
    df_merged["residual_root"] = df_merged["qpu_diff_root"] - df_merged["twin_diff_root"]
    df_merged["residual_full"] = df_merged["qpu_diff_full"] - df_merged["twin_diff_full"]
    return df_merged


def main():
    parser = argparse.ArgumentParser(description="v2.0 Local MPS Digital Twin & QPU Result Merger")
    parser.add_argument("--manifest", type=str, required=True, help="Path to v2_manifest_*.json")
    parser.add_argument("--twin-shots", type=int, default=8192, help="Shots for local MPS simulation")
    parser.add_argument("--fetch-only", action="store_true", help="Skip MPS re-run if twin CSV exists, only fetch QPU")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    out_dir = manifest_path.parent
    stem = manifest_path.stem.replace("v2_manifest_", "v2_results_")
    twin_csv = out_dir / f"{stem}_twin.csv"
    merged_csv = out_dir / f"{stem}_merged.csv"

    if args.fetch_only and twin_csv.exists():
        print(f"[Load] Loading existing Digital Twin baseline -> {twin_csv}")
        df_twin = pd.read_csv(twin_csv)
    else:
        df_twin = run_mps_digital_twin(manifest, args.twin_shots)
        df_twin.to_csv(twin_csv, index=False)
        print(f"[Saved] Digital Twin baseline -> {twin_csv}")

    df_merged = fetch_and_merge_qpu_results(manifest, df_twin)
    if df_merged is not None:
        df_merged.to_csv(merged_csv, index=False)
        print(f"\n[MERGED COMPLETE] Full QPU vs Twin Residual table saved -> {merged_csv}")
        print(
            df_merged[
                ["n_qubits", "twin_diff_root", "qpu_diff_root", "residual_root", "qpu_p_root_hold"]
            ].to_string(index=False)
        )


if __name__ == "__main__":
    main()