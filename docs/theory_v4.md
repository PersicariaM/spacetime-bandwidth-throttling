# Pre-Registered Protocol v4.0: Cross-Architecture Validation on All-to-All Trapped-Ion QPU (`IonQ Forte`)

- **Date:** 2026-11-21 (Pre-Execution Registration)
- **Author:** Jaeyeun Moon (Spacetime Bandwidth Lab)
- **Target Hardware:** `ionq_qpu.forte-1` (All-to-All Connectivity, Trapped-Ion)
- **Reference Ticket:** IonQ Research Credits `#1437`

## 1. Objective & Hypothesis
To isolate **hardware-induced physical wire $ZZ$ crosstalk** (observed on fixed-grid superconducting Heron r2 chips in v3.0–v3.2) from **abstract circuit loop topology**, we execute the exact same 24-qubit GHZ Loschmidt Echo circuits (`0`, `1`, and `2` closed cycles) on IonQ Forte's all-to-all architecture.

- **Hypothesis ($H_1$):** Because trapped-ion qubits interact via shared motional modes without fixed nearest-neighbor planar wiring, adding `1` or `2` closed entanglement cycles will **not** trigger the sharp topological crosstalk collapse seen on 2D superconducting grids; instead, fidelity scaling will track total native 2Q gate count (`46 → 50 → 54`) smoothly.
- **Alternative ($H_2$ — Gate Duration Trade-off):** If survival degrades faster with depth than on IBM Heron r2, the degradation will correlate linearly with native 2Q gate execution duration rather than loop count.

## 2. Experimental Matrix (48 Circuits Total)
- **Qubit Count:** $N = 24$
- **Topologies:** `0_cycle` (`1Q=2, 2Q=46`), `1_cycle` (`1Q=4, 2Q=50`), `2_cycle` (`1Q=6, 2Q=54`)
- **Depth Layers:** `d in [1, 2, 4, 8]` with explicit `delay` barriers
- **Decoupling Modes:** `Unprotected` vs. `Symmetric Echo / DD`
- **Shots per Circuit:** `1024` (Error Mitigation: `OFF` for raw hardware characterization)
- **Estimated Credit Budget:** `$3,024.69` (within approved Research Credits grant; `$0.00` out-of-pocket)

## 3. Falsification & Reporting Commitment
All raw shot distributions, native transpiled gate counts, and Job IDs will be published verbatim regardless of whether $H_1$ or $H_2$ dominates, framing results as an objective architectural trade-off benchmark.
