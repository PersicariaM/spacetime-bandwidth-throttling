# Spacetime Computational Bandwidth Limits & Non-Markovian Decoherence Scaling on Superconducting QPUs

[![DOI (Latest)](https://zenodo.org/badge/DOI/10.5281/zenodo.24345477.svg)](https://doi.org/10.5281/zenodo.24345477)
[![DOI (v2.0.0)](https://zenodo.org/badge/DOI/10.5281/zenodo.24358228.svg)](https://doi.org/10.5281/zenodo.24358228)
[![DOI (v1.0.0)](https://zenodo.org/badge/DOI/10.5281/zenodo.24345478.svg)](https://doi.org/10.5281/zenodo.24345478)

An empirical quantum computing and Site Reliability Engineering (SRE) research project investigating whether physical spacetime enforces a finite entanglement processing bandwidth ceiling ($B_{\max}$), and characterizing multi-qubit decoherence scaling up to **$N = 52$ entangled qubits** on IBM Heron r2 superconducting quantum processors (`ibm_fez`, `ibm_marrakesh`, and `ibm_kingston`).

* **Author:** Jaeyeun Moon (Independent Quantum SRE & Cloud Infrastructure Researcher)
* **Pre-Registration SHA-256 (`theory_v1.md`):** `1C24A6371721543A631272826D64D20570EE249400849E476C300E1C84FF0B45`
* **Manuscript PDF:** [`paper/main.pdf`](paper/main.pdf)

---

## Key Empirical Findings (v1.0.0 $\rightarrow$ v2.0.0)

| Release | Qubit Range ($N$) | QPU Backends (156q Heron r2) | Protocol & Probe | Key Empirical Result & Statistical Significance |
|---|---|---|---|---|
| **v1.0.0** ([DOI](https://doi.org/10.5281/zenodo.24345478)) | $2 \dots 24$ | `ibm_fez`, `ibm_marrakesh` | Direct Full-String Readout $P(0^N)+P(1^N)$ | Unrefocused multi-qubit crosstalk excess ($+4.01\sigma$, $p = 2.98 \times 10^{-5}$); quadratic model ($R^2 = 0.9809$) favored over throttling cliff; initial lower bound **$B_{\max} \ge 44.86\text{ qubits}$**. |
| **v2.0.0** ([DOI](https://doi.org/10.5281/zenodo.24358228)) | $16 \dots 52$ | `ibm_fez`, `ibm_kingston` | Zero-SWAP BFS Tree + GHZ Loschmidt Echo + Symmetric CPMG $[X, X]$ | **$59.91\%$** (`ibm_fez`) & **$59.68\%$** (`ibm_kingston`) survival at $N=52$ (**Pearson $r = 0.9630$, $p = 2.008 \times 10^{-6}$**); refutes $44.86\text{ q}$ threshold; elevates bound to **$B_{\max} \ge 195.89\text{ qubits}$**; confirms CPMG non-Markovian suppression at **$6.36\sigma$** ($t = -11.3599$, $p = 1.987 \times 10^{-10}$). |

---

## Repository Structure

```text
├── theory_v1.md                      # Pre-registered hypothesis & falsification criteria
├── run_v2_high_qubit_qpu.py          # v2.0 0-SWAP BFS tree & GHZ Loschmidt Echo QPU runner
├── run_v2_digital_twin_mps.py        # Live-calibrated 1:1 Qiskit Aer MPS digital twin simulator
├── analyze_v2_cross_chip.py          # Cross-chip statistical testing (6.36σ) & 300 DPI plotting
├── data/
│   └── v2_experiments/               # QPU manifests, calibration snapshots, merged CSVs & JSON summary
└── paper/
    ├── main.pdf                      # Compiled v2.0.0 academic manuscript
    └── figures/                      # 300 DPI publication figures (v2_fig1, v2_fig2)
```

---

## Citation

If you use this dataset, simulation pipeline, or manuscript, please cite:

```bibtex
@misc{moon2026spacetime_v2,
  author       = {Moon, Jaeyeun},
  title        = {Probing Spacetime Computational Bandwidth Limits and Non-Markovian Decoherence Suppression up to 52 Entangled Qubits on Superconducting Quantum Processors},
  year         = {2026},
  publisher    = {Zenodo},
  version      = {v2.0.0},
  doi          = {10.5281/zenodo.24358228},
  url          = {https://doi.org/10.5281/zenodo.24358228}
}
```