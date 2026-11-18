import numpy as np
import pandas as pd
from qiskit import QuantumCircuit, transpile
from qiskit.circuit.library import XGate
from qiskit.transpiler import PassManager
from qiskit.transpiler.passes import ALAPScheduleAnalysis, PadDynamicalDecoupling
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler

# 1. Connect to IBM Quantum service and select target backend
service = QiskitRuntimeService(channel="ibm_cloud")
backend_name = "ibm_marrakesh"
backend = service.backend(backend_name)
print(f"[INFO] Connected replication QPU: {backend.name} ({backend.num_qubits} qubits)")

# 2. Build MPS digital twin simulator
noise_model = NoiseModel.from_backend(backend)
sim_backend = AerSimulator(method="matrix_product_state", noise_model=noise_model)

# 3. Circuit builders (identical to ibm_fez calibrated experiment)
qubit_counts = [2, 4, 6, 8, 12, 16, 20, 24]
idle_ns = 500
dt = backend.dt
idle_dt = int(round((idle_ns * 1e-9) / dt))

def build_control_circuit(n):
    qc = QuantumCircuit(n)
    for i in range(n):
        qc.h(i)
    qc.barrier()
    for i in range(n):
        qc.delay(idle_dt, i, unit="dt")
    qc.barrier()
    for i in range(n):
        qc.h(i)
    qc.measure_all()
    return qc

def build_ghz_circuit(n):
    qc = QuantumCircuit(n)
    qc.h(0)
    for i in range(n - 1):
        qc.cx(i, i + 1)
    qc.barrier()
    for i in range(n):
        qc.delay(idle_dt, i, unit="dt")
    qc.barrier()
    for i in reversed(range(n - 1)):
        qc.cx(i, i + 1)
    qc.h(0)
    qc.measure_all()
    return qc

# 4. Heron r2 native transpile and CPMG dynamical decoupling
target = backend.target
pm_dd = PassManager([
    ALAPScheduleAnalysis(target=target),
    PadDynamicalDecoupling(target=target, dd_sequence=[XGate(), XGate()], pulse_alignment=16)
])

isa_circuits = []
circuit_meta = []

for n in qubit_counts:
    for ctype, builder in [("CTRL", build_control_circuit), ("GHZ", build_ghz_circuit)]:
        raw_qc = builder(n)
        t_qc = transpile(raw_qc, backend=backend, optimization_level=3, seed_transpiler=42)
        dd_qc = pm_dd.run(t_qc)
        isa_circuits.append(dd_qc)
        circuit_meta.append((n, ctype))

print(f"[INFO] Compiled {len(isa_circuits)} ISA + CPMG DD circuits")

# 5. Run fast compact digital twin simulation (using sim_backend native basis_gates)
shots = 2048
sim_results = {}
print("[INFO] Running compact digital twin simulation...")
for (n, ctype), raw_builder in zip(circuit_meta, [build_control_circuit if m[1]=="CTRL" else build_ghz_circuit for m in circuit_meta]):
    compact_qc = transpile(raw_builder(n), basis_gates=["rz", "sx", "x", "cz", "delay", "measure"], optimization_level=3, seed_transpiler=42)
    job_sim = sim_backend.run(compact_qc, shots=shots, seed_simulator=42)
    counts = job_sim.result().get_counts()
    zero_state = "0" * n
    p_success = counts.get(zero_state, 0) / shots
    sim_results[(n, ctype)] = 1.0 - p_success
    print(f"   -> Sim done: N={n:2d} [{ctype}] Err={sim_results[(n, ctype)]:.5f}")

# 6. Submit job to real QPU (ibm_marrakesh)
print(f"[INFO] Submitting job to {backend_name} (Tag: GHZ_State_Benchmark_Replication)...")
sampler = Sampler(mode=backend)
sampler.options.environment.job_tags = ["GHZ_State_Benchmark_Replication"]
job_qpu = sampler.run(isa_circuits, shots=shots)
job_id = job_qpu.job_id()
print(f"[SUBMITTED] Job ID: {job_id} — Waiting for QPU execution...")

qpu_pub_results = job_qpu.result()
qpu_results = {}

for idx, (n, ctype) in enumerate(circuit_meta):
    counts = qpu_pub_results[idx].data.meas.get_counts()
    zero_state = "0" * n
    p_success = counts.get(zero_state, 0) / shots
    qpu_results[(n, ctype)] = 1.0 - p_success

# 7. Aggregate results and save CSV
rows = []
for n in qubit_counts:
    sim_ctrl = sim_results[(n, "CTRL")]
    sim_ghz = sim_results[(n, "GHZ")]
    sim_diff = sim_ghz - sim_ctrl

    qpu_ctrl = qpu_results[(n, "CTRL")]
    qpu_ghz = qpu_results[(n, "GHZ")]
    qpu_diff = qpu_ghz - qpu_ctrl

    residual_anomaly = qpu_diff - sim_diff
    rows.append({
        "N_qubits": n,
        "Sim_Ctrl_Err": round(sim_ctrl, 5),
        "Sim_GHZ_Err": round(sim_ghz, 5),
        "Sim_Diff": round(sim_diff, 5),
        "QPU_Ctrl_Err": round(qpu_ctrl, 5),
        "QPU_GHZ_Err": round(qpu_ghz, 5),
        "QPU_Diff": round(qpu_diff, 5),
        "Residual_Anomaly": round(residual_anomaly, 5)
    })

df_out = pd.DataFrame(rows)
out_csv = f"calibrated_results_{backend_name}_{job_id}.csv"
df_out.to_csv(out_csv, index=False)

print("\n" + "="*65)
print(f"[SUCCESS] {backend_name} replication complete! Saved: {out_csv}")
print("="*65)
print(df_out.to_string(index=False))
