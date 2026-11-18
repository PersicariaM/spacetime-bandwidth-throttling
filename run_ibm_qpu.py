import json
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from qiskit import QuantumCircuit
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler

# 1. 실험 설정 (Phase 2-2 베이스라인과 동일한 조건)
QUBIT_COUNTS = [2, 4, 6, 8, 10, 12, 14, 16]
SHOTS = 4096
IDLE_TIME_NS = 2000
JOB_TAG = "GHZ_State_Benchmark"


def create_control_circuit(n_qubits: int) -> QuantumCircuit:
    """대조군: 비얽힘 다중 중첩 상태 |+>^N"""
    qc = QuantumCircuit(n_qubits, n_qubits, name=f"ctrl_n{n_qubits}")
    qc.h(range(n_qubits))
    qc.barrier()
    for q in range(n_qubits):
        qc.delay(IDLE_TIME_NS, q, unit="ns")
    qc.barrier()
    qc.h(range(n_qubits))
    qc.measure(range(n_qubits), range(n_qubits))
    return qc


def create_ghz_circuit(n_qubits: int) -> QuantumCircuit:
    """실험군: N-큐비트 최대 얽힘(GHZ) 상태"""
    qc = QuantumCircuit(n_qubits, n_qubits, name=f"ghz_n{n_qubits}")
    qc.h(0)
    for i in range(n_qubits - 1):
        qc.cx(i, i + 1)
    qc.barrier()
    for q in range(n_qubits):
        qc.delay(IDLE_TIME_NS, q, unit="ns")
    qc.barrier()
    for i in reversed(range(n_qubits - 1)):
        qc.cx(i, i + 1)
    qc.h(0)
    qc.measure(range(n_qubits), range(n_qubits))
    return qc


def main():
    print("=== Q-SRE Lab: Phase 3-1 Real IBM QPU Experiment ===")
    service = QiskitRuntimeService()

    # 대기열이 가장 짧은 운영 중 QPU 자동 선택 (현재 ibm_fez 예상)
    backend = service.least_busy(simulator=False, operational=True, min_num_qubits=20)
    print(f"Selected QPU: {backend.name} ({backend.num_qubits} qubits, pending: {backend.status().pending_jobs})")

    # 16개 회로 생성 (Control 8개 + GHZ 8개)
    raw_circuits = []
    circuit_meta = []
    for n in QUBIT_COUNTS:
        raw_circuits.append(create_control_circuit(n))
        circuit_meta.append({"group": "Control", "n_qubits": n})
        raw_circuits.append(create_ghz_circuit(n))
        circuit_meta.append({"group": "GHZ", "n_qubits": n})

    # 하드웨어 토폴로지 매핑 및 스케줄링 (delay 보존을 위해 optimization_level=1, scheduling_method='alap' 적용)
    pm = generate_preset_pass_manager(
        backend=backend,
        optimization_level=1,
        scheduling_method="alap",
    )
    isa_circuits = pm.run(raw_circuits)
    print(f"Transpiled {len(isa_circuits)} circuits for {backend.name} ISA.")

    # SamplerV2로 단일 배치 제출
    sampler = Sampler(mode=backend)
    sampler.options.environment.job_tags = [JOB_TAG]
    job = sampler.run(isa_circuits, shots=SHOTS)
    job_id = job.job_id()
    print(f"\n[SUBMITTED] Job ID: {job_id}")
    print("Waiting for QPU execution results... (Do not close terminal, or check status via Job ID later)")

    # Job 메타데이터 우선 저장 (네트워크 끊김 대비)
    meta_record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "backend_name": backend.name,
        "job_id": job_id,
        "shots": SHOTS,
        "idle_time_ns": IDLE_TIME_NS,
        "qubit_counts": QUBIT_COUNTS,
    }
    with open(f"ibm_job_meta_{job_id}.json", "w", encoding="utf-8") as f:
        json.dump(meta_record, f, indent=2)

    # 결과 대기 및 수신
    result = job.result()
    print("[COMPLETED] QPU results received! Parsing counts...")

    rows_by_n = {n: {} for n in QUBIT_COUNTS}
    for idx, meta in enumerate(circuit_meta):
        n = meta["n_qubits"]
        group = meta["group"]
        pub_result = result[idx]
        # Classical register 'c'에서 비트열 카운트 추출
        counts = pub_result.data.c.get_counts()
        target_bitstring = "0" * n
        fidelity = counts.get(target_bitstring, 0) / SHOTS
        error_rate = 1.0 - fidelity
        rows_by_n[n][group] = round(error_rate, 5)

    final_records = []
    for n in QUBIT_COUNTS:
        c_err = rows_by_n[n]["Control"]
        g_err = rows_by_n[n]["GHZ"]
        diff = round(g_err - c_err, 5)
        final_records.append({
            "N_qubits": n,
            "Control_Error_QPU": c_err,
            "GHZ_Error_QPU": g_err,
            "Entanglement_Overhead_QPU": diff,
        })
        print(
            f"[N={n:2d}] QPU Control Err: {c_err:.4f} | "
            f"QPU GHZ Err: {g_err:.4f} | "
            f"QPU Diff: {diff:.4f}"
        )

    df = pd.DataFrame(final_records)
    csv_filename = f"ibm_qpu_results_{backend.name}_{job_id}.csv"
    df.to_csv(csv_filename, index=False)
    print(f"\nSaved QPU experimental data to '{csv_filename}'")


if __name__ == "__main__":
    main()
