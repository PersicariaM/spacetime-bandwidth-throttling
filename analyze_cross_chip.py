import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
from scipy.optimize import curve_fit

# 1. Load both calibrated QPU datasets
fez_file = sorted(glob.glob("calibrated_results_ibm_fez_*.csv"))[-1]
mar_file = sorted(glob.glob("calibrated_results_ibm_marrakesh_*.csv"))[-1]

df_fez = pd.read_csv(fez_file)
df_mar = pd.read_csv(mar_file)

N = df_fez["N_qubits"].values.astype(float)
res_fez = df_fez["Residual_Anomaly"].values.astype(float)
res_mar = df_mar["Residual_Anomaly"].values.astype(float)

qdiff_fez = df_fez["QPU_Diff"].values.astype(float)
qdiff_mar = df_mar["QPU_Diff"].values.astype(float)

# 2. Cross-chip reproducibility correlation & pooled significance
r_res, p_res_corr = stats.pearsonr(res_fez, res_mar)
rho_res, p_res_spearman = stats.spearmanr(res_fez, res_mar)

r_qdiff, p_qdiff_corr = stats.pearsonr(qdiff_fez, qdiff_mar)

# One-sample t-test on ibm_marrakesh residual & pooled residual
t_mar, p_mar_two = stats.ttest_1samp(res_mar, 0.0)
p_mar_one = p_mar_two / 2 if t_mar > 0 else 1.0 - (p_mar_two / 2)

pooled_res = np.concatenate([res_fez, res_mar])
t_pool, p_pool_two = stats.ttest_1samp(pooled_res, 0.0)
p_pool_one = p_pool_two / 2 if t_pool > 0 else 1.0 - (p_pool_two / 2)
z_pool = stats.norm.ppf(1 - p_pool_one)

print("="*68)
print("1. Cross-Chip Reproducibility & Pooled Statistical Significance")
print("="*68)
print(f" - ibm_marrakesh Mean Residual   : {np.mean(res_mar):.4f} +/- {np.std(res_mar, ddof=1):.4f}")
print(f" - ibm_marrakesh One-sided p-val : {p_mar_one:.4e} (t = {t_mar:.4f})")
print(f" - Cross-Chip Pearson r (Resid.) : {r_res:.4f} (p = {p_res_corr:.4e})")
print(f" - Cross-Chip Pearson r (QPU_Diff): {r_qdiff:.4f} (p = {p_qdiff_corr:.4e})")
print(f" - Pooled Residual (n=16) t-stat : {t_pool:.4f}, p = {p_pool_one:.4e} ({z_pool:.2f} sigma)")

# 3. Quadratic SRE Cascading Error Fit on Both Chips
def model_quad(n, a, b, c):
    return a * (n**2) + b * n + c

popt_fez, _ = curve_fit(model_quad, N, res_fez)
popt_mar, _ = curve_fit(model_quad, N, res_mar)

r2_fez = 1 - np.sum((res_fez - model_quad(N, *popt_fez))**2) / np.sum((res_fez - np.mean(res_fez))**2)
r2_mar = 1 - np.sum((res_mar - model_quad(N, *popt_mar))**2) / np.sum((res_mar - np.mean(res_mar))**2)

print("\n" + "="*68)
print("2. SRE Cascading Quadratic Model Comparison Across Heron r2 QPUs")
print("="*68)
print(f" - ibm_fez       : R^2 = {r2_fez:.5f} | params (a, b, c) = {np.round(popt_fez, 5)}")
print(f" - ibm_marrakesh : R^2 = {r2_mar:.5f} | params (a, b, c) = {np.round(popt_mar, 5)}")

# 4. Generate Publication-Ready Figure 2 (Cross-Chip Validation)
plt.rcParams.update({'font.size': 11, 'font.family': 'sans-serif'})
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.2, 5.2), dpi=300)

n_smooth = np.linspace(min(N), max(N), 200)

# Panel A: Pure Entanglement Excess Error (QPU_Diff = QPU_GHZ - QPU_Ctrl)
ax1.plot(N, qdiff_fez, 'o-', color='#D62728', linewidth=2.2, markersize=6.5, label='ibm_fez (156q Heron r2)')
ax1.plot(N, qdiff_mar, 's--', color='#1F77B4', linewidth=2.2, markersize=6.5, label='ibm_marrakesh (156q Heron r2)')
ax1.set_title(f'(a) Cross-Chip Pure Entanglement Error ($r$ = {r_qdiff:.3f})', fontweight='bold')
ax1.set_xlabel('Entangled Qubit Count (N)')
ax1.set_ylabel('Excess Entanglement Error ($E_{GHZ} - E_{Ctrl}$)')
ax1.grid(True, linestyle='--', alpha=0.4)
ax1.legend(frameon=True, fontsize=9.5)

# Panel B: Residual Anomaly & Quadratic SRE Fits
ax2.scatter(N, res_fez, color='#D62728', s=55, zorder=5, label='ibm_fez Residual')
ax2.plot(n_smooth, model_quad(n_smooth, *popt_fez), '-', color='#D62728', linewidth=1.8, alpha=0.85, label=f'ibm_fez Quad Fit ($R^2$={r2_fez:.3f})')

ax2.scatter(N, res_mar, color='#1F77B4', marker='s', s=55, zorder=5, label='ibm_marrakesh Residual')
ax2.plot(n_smooth, model_quad(n_smooth, *popt_mar), '--', color='#1F77B4', linewidth=1.8, alpha=0.85, label=f'ibm_marrakesh Quad Fit ($R^2$={r2_mar:.3f})')

ax2.axhline(0, color='gray', linestyle=':', linewidth=1.2)
ax2.set_title(f'(b) Digital Twin Residual Anomaly (Pooled {z_pool:.2f}$\\sigma$)', fontweight='bold')
ax2.set_xlabel('Entangled Qubit Count (N)')
ax2.set_ylabel('Residual Anomaly (QPU - Digital Twin)')
ax2.grid(True, linestyle='--', alpha=0.4)
ax2.legend(frameon=True, fontsize=9)

plt.tight_layout()
out_fig = "phase4_cross_chip_comparison.png"
plt.savefig(out_fig, dpi=300)
print(f"\n[SUCCESS] Figure 2 saved: {out_fig}")
