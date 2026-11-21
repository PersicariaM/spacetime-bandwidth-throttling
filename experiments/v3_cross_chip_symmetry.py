import argparse
import json
from datetime import datetime
from pathlib import Path
from qiskit import QuantumCircuit, transpile
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

def build_24q_patch_circuit(num_cycles: int, depth_layers: int, use_cpmg: bool, hold_ns: int = 512) -> QuantumCircuit:
    """24큐비트 2D 패치 (1-Cycle 또는 2-Cycle) GHZ Loschmidt Echo 회로 생성"""
    n_qubits = 24
    qc = QuantumCircuit(n_qubits, n_qubits)

    # 1. GHZ 얽힘 생성 (1D 스패닝 트리 + 폐루프 추가)
    qc.h(0)
    for i in range(n_qubits - 1):
        qc.cz(i, i + 1)
    if num_cycles >= 1:
        qc.cz(0, 5)   # 1st Closed Loop
    if num_cycles >= 2:
        qc.cz(6, 11)  # 2nd Closed Loop
    qc.barrier()

    # 2. 홀드 구간 (Unprotected vs CPMG [X, X] + 명시적 delay)
    dt_per_layer = max(16, (hold_ns // 2) // 16 * 16)
    for _ in range(depth_layers):
        if use_cpmg:
            qc.delay(dt_per_layer, range(n_qubits), unit="dt")
            qc.x(range(n_qubits))
            qc.delay(dt_per_layer * 2, range(n_qubits), unit="dt")
            qc.x(range(n_qubits))
            qc.delay(dt_per_layer, range(n_qubits), unit="dt")
        else:
            qc.delay(dt_per_layer * 4, range(n_qubits), unit="dt")
        qc.barrier()

    # 3. 언컴퓨트 (Loschmidt Echo 역연산)
    if num_cycles >= 2:
        qc.cz(6, 11)
    if num_cycles >= 1:
        qc.cz(0, 5)
    for i in reversed(range(n_qubits - 1)):
        qc.cz(i, i + 1)
    qc.h(0)
    qc.measure(range(n_qubits), range(n_qubits))
    return qc

def main():
    parser = argparse.ArgumentParser(description="v3.1 Cross-Chip Symmetry Verification")
    parser.add_argument("--mode", choices=["dry-run", "qpu"], default="dry-run")
    parser.add_argument("--shots", type=int, default=1024)
    args = parser.parse_args()

    service = QiskitRuntimeService(channel="ibm_cloud")
    plan = [
        {"backend": "ibm_kingston", "num_cycles": 2},
        {"backend": "ibm_fez", "num_cycles": 1},
    ]
    depths = [1, 2, 4, 8]
    compiled_plan = []

    for item in plan:
        backend = service.backend(item["backend"])
        circuits = []
        for d in depths:
            for use_cpmg in [False, True]:
                raw_qc = build_24q_patch_circuit(item["num_cycles"], d, use_cpmg)
                isa_qc = transpile(raw_qc, backend=backend, optimization_level=1, seed_transpiler=42)
                circuits.append((d, use_cpmg, isa_qc))
        compiled_plan.append((item, backend, circuits))

        print(f"\n=== [{item['backend']}] {item['num_cycles']}-Cycle ISA 검증 (seed=42 고정) ===")
        for d, use_cpmg, isa_qc in circuits:
            ops = isa_qc.count_ops()
            print(f"  depth={d}, CPMG={str(use_cpmg):5s} | cz={ops.get('cz', 0):3d}, x={ops.get('x', 0):3d}, delay={ops.get('delay', 0):3d}")

    if args.mode == "dry-run":
        print("\n[DRY-RUN 완료] QPU 할당량 소모 0.00.")
        return

    print("\n[주의] IBM Open Plan 무료 할당량 약 1.4 RUs가 소모됩니다.")
    confirm = input("실제 QPU에 제출하려면 'SUBMIT_IBM_QPU'를 입력하세요: ").strip()
    if confirm != "SUBMIT_IBM_QPU":
        print("제출이 취소되었습니다.")
        return

    Path("data").mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    all_results = {"timestamp": ts, "shots": args.shots, "jobs": []}

    for item, backend, circuits in compiled_plan:
        sampler = SamplerV2(mode=backend)
        isa_list = [c[2] for c in circuits]
        job = sampler.run(isa_list, shots=args.shots)
        job_id = job.job_id()
        print(f"\n[제출 완료] {item['backend']} ({item['num_cycles']}-Cycle) -> Job ID: {job_id}")
        print("대기열 및 실행 완료를 기다리는 중... (Ctrl+C로 종료해도 IBM 서버에서 계속 실행됩니다)")

        result = job.result()
        records = []
        for idx, (d, use_cpmg, isa_qc) in enumerate(circuits):
            counts = result[idx].data.c.get_counts()
            p0 = counts.get("0" * 24, 0) / args.shots
            ops = isa_qc.count_ops()
            records.append({
                "depth_layers": d,
                "cpmg": use_cpmg,
                "cz_count": ops.get("cz", 0),
                "x_count": ops.get("x", 0),
                "qpu_p0": round(p0, 6),
            })
            print(f"  depth={d}, CPMG={str(use_cpmg):5s} -> P(|0^24>) = {p0:.4f}")

        all_results["jobs"].append({
            "backend": item["backend"],
            "num_cycles": item["num_cycles"],
            "job_id": job_id,
            "records": records,
        })

    out_path = Path(f"data/v3_1_cross_chip_symmetry_{ts}.json")
    out_path.write_text(json.dumps(all_results, indent=2), encoding="utf-8")
    print(f"\n[전체 완료] 결과 저장됨: {out_path}")

if __name__ == "__main__":
    main()
