import json
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from qiskit import QuantumCircuit, transpile
from qiskit.circuit.library import XGate
from qiskit.transpiler import PassManager
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit.transpiler.passes import ALAPScheduleAnalysis, PadDynamicalDecoupling
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler

# 1. 정밀 보정 파라미터 (천장 포화 방지 및 고큐비트 확장)
QUBIT_COUNTS = [2, 4, 6, 8, 12, 16, 20, 24]
SHOTS = 4096
IDLE_TIME_NS = 500
JOB_TAG = "GHZ_State_Benchmark_Calibrated"


def create_control_circuit(n_qubits: int) -> QuantumCircuit:
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
    print("=== Q-SRE Lab: Phase 3-1B Calibrated Experiment & Digital Twin ===")
    service = QiskitRuntimeService()
    
    # ibm_fez 우선 선택 (이전 실험과 동일 아키텍처 일관성 유지)
    try:
        backend = service.backend("ibm_fez")
        if not backend.status().operational:
            backend = service.least_busy(simulator=False, operational=True, min_num_qubits=28)
    except Exception:
        backend = service.least_busy(simulator=False, operational=True, min_num_qubits=28)

    print(f"Target QPU: {backend.name} (pending jobs: {backend.status().pending_jobs})")

    raw_circuits = []
    circuit_meta = []
    for n in QUBIT_COUNTS:
        raw_circuits.append(create_control_circuit(n))
        circuit_meta.append({"group": "Control", "n_qubits": n})
        raw_circuits.append(create_ghz_circuit(n))
        circuit_meta.append({"group": "GHZ", "n_qubits": n})

    # 하드웨어 최적화 트랜스파일 + XY4 동적 디커플링 적용
    pm = generate_preset_pass_manager(backend=backend, optimization_level=2, scheduling_method="alap")
    isa_circuits = pm.run(raw_circuits)

    dd_sequence = [XGate(), XGate()]
    dd_pm = PassManager([
        ALAPScheduleAnalysis(target=backend.target),
        PadDynamicalDecoupling(target=backend.target, dd_sequence=dd_sequence)
    ])
    isa_circuits = dd_pm.run(isa_circuits)
    print(f"Transpiled & applied XY4 Dynamical Decoupling to {len(isa_circuits)} circuits.")

    # 1) 실제 QPU 실행 제출
    sampler = Sampler(mode=backend)
    sampler.options.environment.job_tags = [JOB_TAG]
    job = sampler.run(isa_circuits, shots=SHOTS)
    job_id = job.job_id()
    print(f"\n[QPU SUBMITTED] Job ID: {job_id}")

    # 2) QPU 대기하는 동안 로컬 PC(32GB RAM)에서 실시간 백엔드 캘리브레이션 기반 디지털 트윈 시뮬레이션 동시 실행
    print("[DIGITAL TWIN] Extracting live backend noise model & running local simulation...")
    live_noise_model = NoiseModel.from_backend(backend)
    sim_backend = AerSimulator(noise_model=live_noise_model, method="matrix_product_state")

    sim_results = {n: {} for n in QUBIT_COUNTS}
    for idx, meta in enumerate(circuit_meta):
        n = meta["n_qubits"]
        group = meta["group"]
        # 시뮬레이터용 회로 변환 (하드웨어 전용 펄스/배리어 정리 후 노이즈 모델 매핑)
        sim_qc = transpile(raw_circuits[idx], sim_backend, optimization_level=1)
        counts = sim_backend.run(sim_qc, shots=SHOTS).result().get_counts()
        err = 1.0 - (counts.get("0" * n, 0) / SHOTS)
        sim_results[n][group] = round(err, 5)
    print("[DIGITAL TWIN] Local calibrated simulation complete!")

    # 3) 실제 QPU 결과 수신
    print("Waiting for real QPU completion...")
    qpu_result = job.result()
    print("[QPU COMPLETED] Parsing real hardware results...\n")

    qpu_results = {n: {} for n in QUBIT_COUNTS}
    for idx, meta in enumerate(circuit_meta):
        n = meta["n_qubits"]
        group = meta["group"]
        counts = qpu_result[idx].data.c.get_counts()
        err = 1.0 - (counts.get("0" * n, 0) / SHOTS)
        qpu_results[n][group] = round(err, 5)

    # 결과 통합 및 잔여 오차(Residual) 1차 산출
    records = []
    for n in QUBIT_COUNTS:
        sim_diff = round(sim_results[n]["GHZ"] - sim_results[n]["Control"], 5)
        qpu_diff = round(qpu_results[n]["GHZ"] - qpu_results[n]["Control"], 5)
        residual = round(qpu_diff - sim_diff, 5)
        records.append({
            "N_qubits": n,
            "Sim_Ctrl_Err": sim_results[n]["Control"],
            "Sim_GHZ_Err": sim_results[n]["GHZ"],
            "Sim_Diff": sim_diff,
            "QPU_Ctrl_Err": qpu_results[n]["Control"],
            "QPU_GHZ_Err": qpu_results[n]["GHZ"],
            "QPU_Diff": qpu_diff,
            "Residual_Anomaly": residual
        })
        print(
            f"[N={n:2d}] QPU_Ctrl:{qpu_results[n]['Control']:.4f} | "
            f"Sim_Diff:{sim_diff:+.4f} vs QPU_Diff:{qpu_diff:+.4f} | "
            f"Residual:{residual:+.4f}"
        )

    df = pd.DataFrame(records)
    filename = f"calibrated_results_{backend.name}_{job_id}.csv"
    df.to_csv(filename, index=False)
    print(f"\nSaved calibrated comparison dataset to '{filename}'")


if __name__ == "__main__":
    main()
