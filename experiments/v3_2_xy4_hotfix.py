import argparse
import json
from datetime import datetime
from pathlib import Path
from qiskit import QuantumCircuit, transpile
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

def build_24q_2cycle_dd_circuit(depth_layers: int, dd_mode: str, hold_ns: int = 512) -> QuantumCircuit:
    """24큐비트 2-Cycle 패치에서 NONE vs CPMG-4([X,X,X,X]) vs XY4([X,Y,X,Y]) 공정 비교"""
    n_qubits = 24
    qc = QuantumCircuit(n_qubits, n_qubits)

    # 1. GHZ 얽힘 생성 + 2 Closed Cycles
    qc.h(0)
    for i in range(n_qubits - 1):
        qc.cz(i, i + 1)
    qc.cz(0, 5)   # 1st Closed Loop
    qc.cz(6, 11)  # 2nd Closed Loop
    qc.barrier()

    # 2. 홀드 구간 (총 지연 시간 hold_ns * depth_layers 동일 유지)
    tau = max(16, (hold_ns // 8) // 16 * 16)
    for _ in range(depth_layers):
        if dd_mode == "NONE":
            qc.delay(tau * 8, range(n_qubits), unit="dt")
        elif dd_mode == "CPMG4":
            qc.delay(tau, range(n_qubits), unit="dt")
            qc.x(range(n_qubits))
            qc.delay(tau * 2, range(n_qubits), unit="dt")
            qc.x(range(n_qubits))
            qc.delay(tau * 2, range(n_qubits), unit="dt")
            qc.x(range(n_qubits))
            qc.delay(tau * 2, range(n_qubits), unit="dt")
            qc.x(range(n_qubits))
            qc.delay(tau, range(n_qubits), unit="dt")
        elif dd_mode == "XY4":
            qc.delay(tau, range(n_qubits), unit="dt")
            qc.x(range(n_qubits))
            qc.delay(tau * 2, range(n_qubits), unit="dt")
            qc.y(range(n_qubits))
            qc.delay(tau * 2, range(n_qubits), unit="dt")
            qc.x(range(n_qubits))
            qc.delay(tau * 2, range(n_qubits), unit="dt")
            qc.y(range(n_qubits))
            qc.delay(tau, range(n_qubits), unit="dt")
        qc.barrier()

    # 3. 언컴퓨트 (Loschmidt Echo 역연산)
    qc.cz(6, 11)
    qc.cz(0, 5)
    for i in reversed(range(n_qubits - 1)):
        qc.cz(i, i + 1)
    qc.h(0)
    qc.measure(range(n_qubits), range(n_qubits))
    return qc

def main():
    parser = argparse.ArgumentParser(description="v3.2 XY4 vs CPMG-4 Hotfix Verification")
    parser.add_argument("--backend", type=str, default="ibm_marrakesh")
    parser.add_argument("--mode", choices=["dry-run", "qpu"], default="dry-run")
    parser.add_argument("--shots", type=int, default=1024)
    args = parser.parse_args()

    service = QiskitRuntimeService(channel="ibm_cloud")
    backend = service.backend(args.backend)
    depths = [1, 2, 4, 8]
    modes = ["NONE", "CPMG4", "XY4"]

    circuits = []
    for d in depths:
        for m in modes:
            raw_qc = build_24q_2cycle_dd_circuit(d, m)
            isa_qc = transpile(raw_qc, backend=backend, optimization_level=1, seed_transpiler=42)
            circuits.append((d, m, isa_qc))

    print(f"=== [{args.backend}] 2-Cycle CPMG-4 vs XY4 ISA 검증 (총 12회로, seed=42) ===")
    for d, m, isa_qc in circuits:
        ops = isa_qc.count_ops()
        print(f"  depth={d}, mode={m:5s} | cz={ops.get('cz', 0):3d}, x={ops.get('x', 0):3d}, rz={ops.get('rz', 0):3d}, delay={ops.get('delay', 0):3d}")

    if args.mode == "dry-run":
        print("\n[DRY-RUN 완료] QPU 할당량 소모 0.00. CPMG4와 XY4의 cz/x 물리 펄스 수가 동일한지 확인하세요.")
        return

    print(f"\n[주의] {args.backend}에서 IBM Open Plan 무료 할당량 약 0.1~0.2 RUs가 소모됩니다.")
    confirm = input("실제 QPU에 제출하려면 'SUBMIT_XY4_QPU'를 입력하세요: ").strip()
    if confirm != "SUBMIT_XY4_QPU":
        print("제출이 취소되었습니다.")
        return

    Path("data").mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    sampler = SamplerV2(mode=backend)
    isa_list = [c[2] for c in circuits]
    job = sampler.run(isa_list, shots=args.shots)
    job_id = job.job_id()
    print(f"\n[제출 완료] {args.backend} (XY4 Hotfix) -> Job ID: {job_id}")
    print("대기열 및 실행 완료를 기다리는 중...")

    result = job.result()
    records = []
    for idx, (d, m, isa_qc) in enumerate(circuits):
        counts = result[idx].data.c.get_counts()
        p0 = counts.get("0" * 24, 0) / args.shots
        ops = isa_qc.count_ops()
        records.append({
            "depth_layers": d,
            "dd_mode": m,
            "cz_count": ops.get("cz", 0),
            "x_count": ops.get("x", 0),
            "rz_count": ops.get("rz", 0),
            "qpu_p0": round(p0, 6),
        })
        print(f"  depth={d}, mode={m:5s} -> P(|0^24>) = {p0:.4f}")

    out_path = Path(f"data/v3_2_xy4_hotfix_{args.backend}_{ts}.json")
    out_path.write_text(json.dumps({
        "timestamp": ts,
        "backend": args.backend,
        "num_cycles": 2,
        "shots": args.shots,
        "job_id": job_id,
        "records": records,
    }, indent=2), encoding="utf-8")
    print(f"\n[전체 완료] 결과 저장됨: {out_path}")

if __name__ == "__main__":
    main()
