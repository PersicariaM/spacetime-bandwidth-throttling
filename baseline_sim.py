import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from qiskit_aer.noise import (
    NoiseModel,
    thermal_relaxation_error,
    depolarizing_error,
    ReadoutError,
)

# 1. 실험 파라미터 설정 (IBM 초전도 QPU 평균 스펙 모사)
QUBIT_COUNTS = [2, 4, 6, 8, 10, 12, 14, 16]  # 로컬 32GB RAM 고속 연산 구간
SHOTS = 8192                                 # 통계적 오차(1/sqrt(N)) ~ 1.1% 이내 확보
IDLE_TIME_NS = 2000                          # 얽힘 상태 유지 대기 시간 (2 마이크로초)

# 표준 IBM Heron/Eagle 급 평균 물리 노이즈 상수
T1_NS = 150_000.0        # 에너지 완화 시간 (150 us)
T2_NS = 120_000.0        # 위상 결어긋남 시간 (120 us)
TIME_1Q_NS = 35.0        # 단일 큐비트 게이트 시간 (35 ns)
TIME_2Q_NS = 60.0        # 2큐비트(CX) 게이트 시간 (60 ns)
ERR_1Q = 0.0003          # 1큐비트 탈분극 오류율 (0.03%)
ERR_2Q = 0.005           # 2큐비트 탈분극 오류율 (0.5%)
ERR_READOUT = 0.015      # 측정 판독 오류율 (1.5%)


def build_realistic_noise_model() -> NoiseModel:
    """표준 열적 완화(T1, T2) + 게이트 탈분극 + 판독 오류 모델 생성"""
    noise_model = NoiseModel()

    # 1큐비트 게이트 노이즈 (열적 완화 + 탈분극 합성)
    th_1q = thermal_relaxation_error(T1_NS, T2_NS, TIME_1Q_NS)
    dep_1q = depolarizing_error(ERR_1Q, 1)
    error_1q = th_1q.compose(dep_1q)

    # 2큐비트 게이트 노이즈 (양쪽 큐비트 열적 완화 텐서곱 + 2Q 탈분극)
    th_2q = thermal_relaxation_error(T1_NS, T2_NS, TIME_2Q_NS).tensor(
        thermal_relaxation_error(T1_NS, T2_NS, TIME_2Q_NS)
    )
    dep_2q = depolarizing_error(ERR_2Q, 2)
    error_2q = th_2q.compose(dep_2q)

    # 대기(Delay) 구간 노이즈 (순수 T1/T2 환경 결어긋남)
    error_delay = thermal_relaxation_error(T1_NS, T2_NS, IDLE_TIME_NS)

    # 판독(Readout) 혼동 행렬
    ro_error = ReadoutError([
        [1 - ERR_READOUT, ERR_READOUT],
        [ERR_READOUT, 1 - ERR_READOUT]
    ])

    noise_model.add_all_qubit_quantum_error(error_1q, ["h", "x", "sx", "rz"])
    noise_model.add_all_qubit_quantum_error(error_2q, ["cx"])
    noise_model.add_all_qubit_quantum_error(error_delay, ["delay"])
    noise_model.add_all_qubit_readout_error(ro_error)

    return noise_model


def create_control_circuit(n_qubits: int) -> QuantumCircuit:
    """대조군: 비얽힘 다중 중첩 상태 |+>^N 생성 및 동일 대기 시간 적용 후 X-기저 측정"""
    qc = QuantumCircuit(n_qubits, n_qubits)
    qc.h(range(n_qubits))
    qc.barrier()
    for q in range(n_qubits):
        qc.delay(IDLE_TIME_NS, q, unit="ns")
    qc.barrier()
    qc.h(range(n_qubits))  # 이상적 노이즈 0일 때 모든 큐비트가 '0'으로 복원되어야 함
    qc.measure(range(n_qubits), range(n_qubits))
    return qc


def create_ghz_circuit(n_qubits: int) -> QuantumCircuit:
    """실험군: N-큐비트 최대 얽힘(GHZ) 상태 생성 및 동일 대기 시간 적용 후 Parity 측정"""
    qc = QuantumCircuit(n_qubits, n_qubits)
    qc.h(0)
    for i in range(n_qubits - 1):
        qc.cx(i, i + 1)
    qc.barrier()
    for q in range(n_qubits):
        qc.delay(IDLE_TIME_NS, q, unit="ns")
    qc.barrier()
    # 역연산(Uncompute)으로 위상/진폭 붕괴 여부를 '00...0' 복원율로 정밀 측정
    for i in reversed(range(n_qubits - 1)):
        qc.cx(i, i + 1)
    qc.h(0)
    qc.measure(range(n_qubits), range(n_qubits))
    return qc


def main():
    print("=== Q-SRE Lab: Phase 2-2 Baseline Noise Simulation Start ===")
    noise_model = build_realistic_noise_model()
    simulator = AerSimulator(noise_model=noise_model, method="density_matrix")

    records = []
    for n in QUBIT_COUNTS:
        # 12큐비트 초과 시 메모리 보호를 위해 statevector/automatic 전환
        if n > 12:
            simulator = AerSimulator(noise_model=noise_model, method="automatic")

        ctrl_qc = transpile(create_control_circuit(n), simulator, optimization_level=0)
        ghz_qc = transpile(create_ghz_circuit(n), simulator, optimization_level=0)

        ctrl_counts = simulator.run(ctrl_qc, shots=SHOTS).result().get_counts()
        ghz_counts = simulator.run(ghz_qc, shots=SHOTS).result().get_counts()

        target_bitstring = "0" * n
        ctrl_fidelity = ctrl_counts.get(target_bitstring, 0) / SHOTS
        ghz_fidelity = ghz_counts.get(target_bitstring, 0) / SHOTS

        ctrl_error = 1.0 - ctrl_fidelity
        ghz_error = 1.0 - ghz_fidelity
        diff_error = ghz_error - ctrl_error

        records.append({
            "N_qubits": n,
            "Control_Error_Sim": round(ctrl_error, 5),
            "GHZ_Error_Sim": round(ghz_error, 5),
            "Entanglement_Overhead_Sim": round(diff_error, 5),
        })
        print(
            f"[N={n:2d}] Control Err: {ctrl_error:.4f} | "
            f"GHZ Err: {ghz_error:.4f} | "
            f"Diff (GHZ - Ctrl): {diff_error:.4f}"
        )

    df = pd.DataFrame(records)
    df.to_csv("baseline_simulation_results.csv", index=False)
    print("\nSaved data to 'baseline_simulation_results.csv'")

    # 시각화 그래프 저장
    plt.figure(figsize=(9, 5.5))
    plt.plot(df["N_qubits"], df["Control_Error_Sim"], "o--", label="Control Group (Unentangled |+>^N)")
    plt.plot(df["N_qubits"], df["GHZ_Error_Sim"], "s-", linewidth=2, label="Experimental Group (GHZ_N Entangled)")
    plt.plot(df["N_qubits"], df["Entanglement_Overhead_Sim"], "^:", label="Pure Entanglement Overhead (GHZ - Control)")
    plt.title("Phase 2-2 Baseline Simulation: Standard Noise Model (T1, T2, Gate, Readout)")
    plt.xlabel("Number of Qubits (N)")
    plt.ylabel("State Infidelity / Error Rate (1 - P_00...0)")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig("baseline_error_curve.png", dpi=150)
    print("Saved plot to 'baseline_error_curve.png'")


if __name__ == "__main__":
    main()
