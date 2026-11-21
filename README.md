# Spacetime Bandwidth Throttling (`Moon-QProbe`)

**Empirical Cross-Architecture Quantum SRE Benchmark: Fixed-Grid Superconducting (`IBM Heron r2`) vs. All-to-All Trapped-Ion (`IonQ Forte`)**

- **Live Benchmark Dashboard:** https://persicariam.github.io/spacetime-bandwidth-throttling/
- **Concept DOI (All Versions):** [10.5281/zenodo.24345477](https://doi.org/10.5281/zenodo.24345477)
- **Latest Archived Manuscript (`v3.0.0`):** [10.5281/zenodo.24393862](https://doi.org/10.5281/zenodo.24393862)
- **Author:** Jaeyeun Moon (Independent Researcher, Spacetime Bandwidth Lab)

---

## Core Empirical Milestones

1. **v1.0.0 — Multi-Qubit Entanglement Scaling (`N = 2..24`):**
   Demonstrated quadratic error accumulation ($R^2 = 0.9809$) and $4.01\sigma$ deviation from standard Markovian digital twins across `ibm_fez` and `ibm_marrakesh`, establishing an initial spacetime bandwidth lower bound of $B_{\max} \ge 44.86\text{ qubits}$.
2. **v2.0.0 — Non-Markovian CPMG Suppression up to `N = 52`:**
   Achieved `59.91%` (`ibm_fez`) and `59.68%` (`ibm_kingston`) GHZ Loschmidt Echo survival at $N=52$ using 0-SWAP BFS trees + symmetric CPMG `[X, X]` decoupling ($6.36\sigma$ suppression, $r = 0.9630$), raising the lower bound to $B_{\max} \ge 195.89\text{ qubits}$.
3. **v3.0.0 – v3.2 — 2D Closed-Loop Sign Inversion & `XY4` Triple-Chip Validation (`N = 24`):**
   - **Topological Sign Inversion (`0 → 1 → 2` Cycles):** Introducing closed entanglement loops on 2D superconducting patches inverts CPMG from noise suppression (`-0.0548`) to net degradation (`+0.0213`, $p = 0.0172$), confirmed across `ibm_fez`, `ibm_kingston`, and `ibm_marrakesh`.
   - **Multi-Axis `XY4` vs. `CPMG-4` Control:** Under identical physical pulse budgets (`cz=119`, `x=96..768`, `seed_transpiler=42`), `XY4` outperformed `CPMG-4` in **8 / 8** depth conditions across `ibm_kingston` and `ibm_marrakesh` (up to `2.03x` survival at `depth=8`), yet remained below the unprotected baseline due to fixed-grid $ZZ$ crosstalk.
4. **v4.0.0 — All-to-All Trapped-Ion Cross-Validation (`IonQ Forte`, Pending):**
   Pre-registered protocol (`docs/theory_v4.md`) and pre-flight simulator validation completed (Ticket `#1437`) to isolate physical wire crosstalk from circuit loop topology.

---

## Repository Structure

- `docs/index.html` — Static `Moon-QProbe` interactive benchmark dashboard (GitHub Pages)
- `docs/theory_v4.md` — Pre-registered v4.0 experimental protocol & falsification criteria
- `experiments/` — Reproducible Qiskit circuits (`v3_cross_chip_symmetry.py`, `v3_2_xy4_hotfix.py`, `v4_ionq_preflight_sim.py`, `v4_ionq_qpu_run.py`)
- `data/` — Raw JSON/CSV QPU measurements and Job IDs
- `paper/` — LaTeX manuscript sources and 300 DPI figures
