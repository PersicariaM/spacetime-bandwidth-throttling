# Pre-Registered Protocol v4.0: Cross-Architecture Validation on All-to-All Trapped-Ion QPU (`IonQ Forte`)

- **Date:** 2026-11-22 (Red-Team Hardened Pre-Execution Registration)
- **Author:** Jaeyeun Moon (Spacetime Bandwidth Lab)
- **Target Hardware:** `ionq_qpu.forte-1` (All-to-All Connectivity, Trapped-Ion)
- **Reference Ticket:** IonQ Research Credits `#1437`

## 1. Objective & Hypothesis
To isolate **hardware-induced physical wire $ZZ$ crosstalk** (observed on fixed-grid superconducting Heron r2 chips in v3.0–v3.2) from **abstract circuit loop topology**, we execute the exact same 24-qubit GHZ Loschmidt Echo circuits (`0`, `1`, and `2` closed cycles) on IonQ Forte's all-to-all architecture.

- **Hypothesis ($H_1$):** Because trapped-ion qubits interact via shared motional modes without fixed nearest-neighbor planar wiring, adding `1` or `2` closed entanglement cycles will **not** trigger the sharp topological crosstalk collapse seen on 2D superconducting grids; instead, fidelity scaling will track total native 2Q gate count (`46 -> 50 -> 54`) smoothly without sign inversion in dynamical decoupling gain.
- **Alternative ($H_2$ – Gate Duration Trade-off):** If survival degrades faster with depth than on IBM Heron r2, the degradation will correlate linearly with native 2Q gate execution duration rather than closed-loop count.

## 2. Experimental Matrix & Two-Stage Canary Execution
- **Qubit Count:** $N = 24$
- **Topologies:** `0_cycle` (`1Q=2, 2Q=46`), `1_cycle` (`1Q=4, 2Q=50`), `2_cycle` (`1Q=6, 2Q=54`)
- **Depth Layers:** `d in [1, 2, 4, 8]` with explicit `delay` barriers
- **Decoupling Modes:** `Unprotected` vs. `Symmetric Echo / DD`
- **Shots per Circuit:** `1024` (Error Mitigation: `OFF` for raw hardware characterization)
- **Two-Stage Canary & Drift-Guard Schedule (`49` total submissions, `$3,087.49` within `$3,200.00` cap, `$0.00` out-of-pocket):**
  - **Stage 1 (`--stage canary`, 6 boundary circuits, `$378.06`):** Extreme corners `(cycle in {0, 2}, depth=1/8, echo=False/True)` to validate native compilation, JSON schema, and worst-case pulse load prior to full commitment.
  - **Stage 2 (`--stage remaining`, 42 remaining circuits + 1 duplicate baseline anchor, `$2,709.43`):** Re-executes `(rep=0, cycle=0, depth=1, echo=False)` as an inter-batch calibration anchor to verify hardware stability across stages.

## 3. Fair Cross-Architecture Evaluation Metric (Relative Slope Criterion)
Because superconducting ($\text{ns}$-scale) and trapped-ion ($\mu\text{s}$-scale) architectures differ by orders of magnitude in native 2Q gate duration, absolute `Unprotected` baseline survival ($P_{0,\text{NONE}}$) is not compared directly as a raw superiority score. Instead, cross-architecture equivalence is evaluated via the **relative dynamical decoupling protection margin** $\Delta P_0 = P_{0,\text{DD}} - P_{0,\text{NONE}}$ and its topological slope $\partial (\Delta P_0) / \partial N_{\text{cycles}}$ across `0 -> 1 -> 2` closed cycles (testing whether the sign inversion observed on IBM Heron r2 vanishes on an all-to-all bus).

## 4. Falsification & Reporting Commitment
All raw shot distributions, native transpiled gate counts, inter-batch anchor deltas, and Job IDs will be published verbatim regardless of whether $H_1$ or $H_2$ dominates, framing results as an objective architectural trade-off benchmark.
