import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from qiskit import QuantumCircuit, transpile
from qiskit_ionq import IonQProvider

# 3중 과금 방어 상수
MAX_ALLOWED_USD = 3200.00
ESTIMATED_COST_PER_CIRCUIT_USD = 63.01

def build_v4_ionq_circuit(num_cycles: int, depth_layers: int, use_echo: bool, hold_ns: int = 512) -> QuantumCircuit:
    n_qubits = 24
    qc = QuantumCircuit(n_qubits, n_qubits)

    qc.h(0)
    for i in range(n_qubits - 1):
        qc.cx(i, i + 1)
    if num_cycles >= 1:
        qc.cx(0, 5)
    if num_cycles >= 2:
        qc.cx(6, 11)
    qc.barrier()

    dt_half = hold_ns // 2
    for _ in range(depth_layers):
        if use_echo:
            qc.delay(dt_half, range(n_qubits), unit="ns")
            qc.x(range(n_qubits))
            qc.delay(hold_ns, range(n_qubits), unit="ns")
            qc.x(range(n_qubits))
            qc.delay(dt_half, range(n_qubits), unit="ns")
        else:
            qc.delay(hold_ns * 2, range(n_qubits), unit="ns")
        qc.barrier()

    if num_cycles >= 2:
        qc.cx(6, 11)
    if num_cycles >= 1:
        qc.cx(0, 5)
    for i in reversed(range(n_qubits - 1)):
        qc.cx(i, i + 1)
    qc.h(0)
    qc.measure(range(n_qubits), range(n_qubits))
    return qc

def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="v4.0 IonQ Forte QPU Benchmark (3-Layer Billing Guard)")
    parser.add_argument("--mode", choices=["dry-run", "sim", "qpu"], default="dry-run")
    parser.add_argument("--shots", type=int, default=1024)
    parser.add_argument("--repeats", type=int, default=2, help="Repetitions per (cycle, depth, echo) point")
    args = parser.parse_args()

    cycles_list = [0, 1, 2]
    depths = [1, 2, 4, 8]
    echo_modes = [False, True]

    plan = []
    for rep in range(args.repeats):
        for c in cycles_list:
            for d in depths:
                for e in echo_modes:
                    qc = build_v4_ionq_circuit(c, d, e)
                    plan.append((rep, c, d, e, qc))

    total_circuits = len(plan)
    est_usd = round(total_circuits * ESTIMATED_COST_PER_CIRCUIT_USD, 2)

    print(f"=== [v4.0 IonQ Forte Plan] 총 {total_circuits}개 회로 | 예상 크레딧: ${est_usd:.2f} (상한: ${MAX_ALLOWED_USD:.2f}) ===")
    if est_usd > MAX_ALLOWED_USD:
        raise ValueError(f"[과금 방어 차단] 예상 비용(${est_usd})이 안전 상한(${MAX_ALLOWED_USD})을 초과했습니다!")

    if args.mode == "dry-run":
        for _, c, d, e, qc in plan[:6]:
            ops = qc.count_ops()
            print(f"  sample cycle={c}, depth={d}, echo={str(e):5s} | cx={ops.get('cx', 0)}, x={ops.get('x', 0)}, delay={ops.get('delay', 0)}")
        print("\n[DRY-RUN 완료] API 호출 0건, 크레딧 소모 $0.00. 본실험 준비 완료.")
        return

    api_key = os.getenv("IONQ_API_KEY")
    if not api_key:
        raise RuntimeError(".env 파일에서 IONQ_API_KEY를 찾을 수 없습니다.")

    provider = IonQProvider(api_key)
    if args.mode == "sim":
        backend = provider.get_backend("ionq_simulator")
        backend.set_options(noise_model="forte-1")
        print("[SIM 모드] 무료 Forte-1 노이즈 시뮬레이터로 검증을 실행합니다 ($0.00).")
    else:
        print(f"\n[경고] 유료 IonQ Forte QPU에 {total_circuits}개 회로를 제출합니다 (예상 크레딧 차감: ${est_usd:.2f}).")
        confirm = input("승인된 연구 크레딧으로 실행하려면 'EXECUTE_IONQ'를 정확히 입력하세요: ").strip()
        if confirm != "EXECUTE_IONQ":
            print("실행이 안전하게 취소되었습니다.")
            return
        backend = provider.get_backend("ionq_qpu.forte-1")

    Path("data").mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = []

    for idx, (rep, c, d, e, qc) in enumerate(plan):
        isa_qc = transpile(qc, backend=backend, optimization_level=1, seed_transpiler=42)
        job = backend.run(isa_qc, shots=args.shots)
        job_id = job.job_id()
        counts = job.result().get_counts()
        p0 = counts.get("0" * 24, 0) / args.shots
        print(f"  [{idx+1}/{total_circuits}] rep={rep} cycle={c} depth={d} echo={e} -> P0={p0:.4f} (Job: {job_id})")
        results.append({
            "rep": rep, "num_cycles": c, "depth_layers": d, "echo": e,
            "job_id": job_id, "p0": round(p0, 6)
        })

    out_path = Path(f"data/v4_ionq_{args.mode}_{ts}.json")
    out_path.write_text(json.dumps({
        "timestamp": ts, "mode": args.mode, "shots": args.shots,
        "estimated_usd": est_usd, "records": results
    }, indent=2), encoding="utf-8")
    print(f"\n[완료] 결과 저장됨: {out_path}")

if __name__ == "__main__":
    main()
