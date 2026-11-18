# \# Empirical Characterization of Multi-Qubit Entanglement Error Scaling and Experimental Lower Bounds on Spacetime Computational Bandwidth

# 

# \[!\[Pre-registration SHA-256](https://img.shields.io/badge/Pre--registration-SHA256\_Verified-blue)](#pre-registration--integrity)

# \[!\[Hardware](https://img.shields.io/badge/IBM\_Quantum-Heron\_r2\_(156q)-purple)](#experimental-datasets)

# 

# \## Overview

# This repository contains the pre-registered research protocol, Qiskit execution scripts, raw IBM Quantum hardware measurement datasets, statistical analysis pipelines, and LaTeX manuscript for investigating non-linear multi-qubit Greenberger–Horne–Zeilinger (GHZ) entanglement error scaling on superconducting quantum processors (`ibm\_fez` and `ibm\_marrakesh`).

# 

# Using a Site Reliability Engineering (SRE) cascading-failure framework combined with Carr–Purcell–Meiboom–Gill (CPMG) dynamical decoupling and real-time Matrix Product State (MPS) digital twins, we demonstrate:

# 1\. \*\*Statistically Significant Excess Entanglement Residuals:\*\* Pooled across both 156-qubit Heron r2 processors ($n=16$ scaling points, $N \\in \[2, 24]$), hardware GHZ decoherence exceeds calibrated digital-twin predictions ($t = 5.5120$, one-sided $p = 2.9846 \\times 10^{-5}$, $4.01\\sigma$), with strong cross-chip reproducibility ($r = 0.9082$ for differential error, $r = 0.8574$ for residuals).

# 2\. \*\*SRE Quadratic Cascading Error Model:\*\* Model selection via AIC/BIC favors a quadratic cascading-failure model ($R^2 = 0.98087$, $\\text{AIC} = -54.05$ on `ibm\_fez`) over exponential divergence in the $N \\le 24$ regime.

# 3\. \*\*Experimental Lower Bound on Spacetime Computational Bandwidth:\*\* In accordance with pre-registered falsification criteria, the upper envelope establishes an empirical lower bound of \*\*$B\_{\\max} \\ge 44.86\\text{ entangled qubits}$\*\* for $500\\text{ ns}$ coherence windows.

# 

# \## Pre-Registration \& Integrity

# To prevent confirmation bias, the theoretical hypothesis and falsification thresholds were committed prior to hardware execution (`theory\_v1.md`):

# \- \*\*SHA-256 Hash:\*\* `1C24A6371721543A631272826D64D20570EE249400849E476C300E1C84FF0B45`

# 

# \## Experimental Datasets

# | Processor | Architecture | Job ID | Qubit Range ($N$) | Shots | Dataset File |

# | :--- | :--- | :--- | :---: | :---: | :--- |

# | `ibm\_fez` | Heron r2 (156q) | `dbuq31darooc73fkdjhg` | $2 \\dots 16$ | 4,096 | `ibm\_qpu\_results\_ibm\_fez\_dbuq31darooc73fkdjhg.csv` |

# | `ibm\_fez` | Heron r2 (156q) | `dbuq6a7f8rhs73bmom30` | $2 \\dots 24$ | 4,096 | `calibrated\_results\_ibm\_fez\_dbuq6a7f8rhs73bmom30.csv` |

# | `ibm\_marrakesh` | Heron r2 (156q) | `dbur4uv82tmc73dtumr0` | $2 \\dots 24$ | 4,096 | `calibrated\_results\_ibm\_marrakesh\_dbur4uv82tmc73dtumr0.csv` |

# 

# \## Repository Structure

# \- `theory\_v1.md`: Pre-registered theoretical framework and falsification criteria.

# \- `baseline\_sim.py`: Qiskit Aer MPS baseline noise simulation script.

# \- `run\_ibm\_qpu.py` / `run\_calibrated\_experiment.py` / `run\_marrakesh\_replication.py`: Hardware execution scripts with CPMG dynamical decoupling.

# \- `analyze\_residuals.py` / `analyze\_cross\_chip.py`: Statistical testing ($t$-test, Spearman $\\rho$, Pearson $r$), AIC/BIC model selection, and figure generation.

# \- `paper/main.pdf`: Full manuscript PDF.

# 

# \## Author

# \*\*Jaeyeun Moon\*\* — Independent Quantum SRE \& Cloud Infrastructure Research

