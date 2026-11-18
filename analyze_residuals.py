import os
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
from scipy.optimize import curve_fit

# 1. 최신 보정 실험 CSV 자동 탐색 및 로드
csv_files = sorted(glob.glob("calibrated_results_ibm_fez_*.csv"))
if not csv_files:
    raise FileNotFoundError("calibrated_results_ibm_fez_*.csv 파일을 찾을 수 없습니다.")
target_csv = csv_files[-1]
print(f"[INFO] 분석 대상 데이터 로드: {target_csv}")

df = pd.read_csv(target_csv)
print("\n[데이터 컬럼 확인]:", list(df.columns))
print(df.head())

# 컬럼명 자동 매핑 (파일 구조에 맞춰 유연하게 처리)
col_n = [c for c in df.columns if 'qubit' in c.lower() or c.lower() in ['n', 'num_qubits']][0]
col_res = [c for c in df.columns if 'residual' in c.lower()][0]

# QPU 실험군 및 디지털 트윈 예측값 컬럼 탐색
qpu_exp_candidates = [c for c in df.columns if ('qpu' in c.lower() or 'exp' in c.lower()) and 'ctrl' not in c.lower() and 'sim' not in c.lower() and 'twin' not in c.lower()]
twin_exp_candidates = [c for c in df.columns if ('twin' in c.lower() or 'sim' in c.lower()) and 'ctrl' not in c.lower()]

N = df[col_n].values.astype(float)
residual = df[col_res].values.astype(float)

# 2. 통계적 유의성 검정 (귀무가설 H0: Residual 평균 = 0, 즉 디지털 트윈과 차이 없음)
t_stat, p_val_two = stats.ttest_1samp(residual, 0.0)
p_val_one = p_val_two / 2 if t_stat > 0 else 1.0 - (p_val_two / 2)
z_equiv = stats.norm.ppf(1 - p_val_one) if p_val_one < 0.5 else 0.0

# 구간별 단조 증가 추세 검정 (Spearman 순위 상관계수)
rho, p_spearman = stats.spearmanr(N, residual)

print("\n" + "="*60)
print("1. 통계적 유의성 검정 결과 (H0: Residual = 0)")
print("="*60)
print(f" - 잔여 오차 평균 (Mean Residual) : {np.mean(residual):.4f} ± {np.std(residual, ddof=1):.4f}")
print(f" - 일표본 t-통계량 (t-statistic)  : {t_stat:.4f}")
print(f" - 단측 p-value (Residual > 0)    : {p_val_one:.4e} (신뢰수준 약 {z_equiv:.2f} sigma)")
print(f" - 큐비트 수(N) 비례 단조증가(rho) : {rho:.4f} (p = {p_spearman:.4e})")

# 3. 3대 경쟁 모델 비선형 곡선 피팅 (Linear vs Quadratic Crosstalk vs Gravity Throttling)
def model_linear(n, a, b):
    return a * n + b

def model_quad(n, a, b, c):
    return a * (n**2) + b * n + c

def model_throttling(n, amp, b_max, offset):
    # Gamma_grav 형태: amp * exp(-(B_max - n) / n) + offset (n <= B_max 구간 유효)
    return amp * np.exp(-(b_max - n) / n) + offset

def calc_metrics(y_true, y_pred, k_params):
    n_obs = len(y_true)
    rss = np.sum((y_true - y_pred) ** 2)
    tss = np.sum((y_true - np.mean(y_true)) ** 2)
    r2 = 1 - (rss / tss)
    # 정규 오차 가정 기반 AIC / BIC 산출
    aic = n_obs * np.log(rss / n_obs) + 2 * k_params
    bic = n_obs * np.log(rss / n_obs) + k_params * np.log(n_obs)
    return r2, rss, aic, bic

results_summary = []

# (A) 선형 모델
popt_lin, _ = curve_fit(model_linear, N, residual)
pred_lin = model_linear(N, *popt_lin)
r2_lin, rss_lin, aic_lin, bic_lin = calc_metrics(residual, pred_lin, 2)
results_summary.append(("Model 1: Linear Noise (aN + b)", r2_lin, rss_lin, aic_lin, bic_lin, popt_lin))

# (B) 2차 다항식 모델 (기존 하드웨어 크로스토크 대표 모델)
popt_quad, _ = curve_fit(model_quad, N, residual)
pred_quad = model_quad(N, *popt_quad)
r2_quad, rss_quad, aic_quad, bic_quad = calc_metrics(residual, pred_quad, 3)
results_summary.append(("Model 2: Quadratic Crosstalk (aN^2 + bN + c)", r2_quad, rss_quad, aic_quad, bic_quad, popt_quad))

# (C) 중력 스로틀링 지수 모델 (B_max 탐색)
try:
    popt_thr, pcov_thr = curve_fit(
        model_throttling, N, residual,
        p0=[0.6, max(N)*1.2, 0.0],
        bounds=([0.0, max(N)*0.8, -0.5], [10.0, 200.0, 0.5]),
        maxfev=10000
    )
    pred_thr = model_throttling(N, *popt_thr)
    r2_thr, rss_thr, aic_thr, bic_thr = calc_metrics(residual, pred_thr, 3)
    results_summary.append(("Model 3: Spacetime Throttling (Exp)", r2_thr, rss_thr, aic_thr, bic_thr, popt_thr))
    thr_fit_ok = True
except Exception as e:
    print(f"[WARN] 지수 모델 피팅 수렴 경고: {e}")
    thr_fit_ok = False

print("\n" + "="*60)
print("2. 경쟁 모델 적합도 비교 (낮은 AIC/BIC, 높은 R^2가 우세)")
print("="*60)
for name, r2, rss, aic, bic, params in results_summary:
    print(f"[{name}]")
    print(f"   R^2 = {r2:.5f} | RSS = {rss:.5f} | AIC = {aic:.2f} | BIC = {bic:.2f}")
    print(f"   Fitted Params: {np.round(params, 5)}")

if thr_fit_ok:
    print(f"\n[추정된 임계 연산 대역폭 한계 B_max (Qubit 환산)]: {popt_thr[1]:.2f} qubits")

# 4. 논문용 고해상도 2-패널 그래프 생성
plt.rcParams.update({'font.size': 11, 'font.family': 'sans-serif'})
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2), dpi=300)

# Panel A: QPU 실측 오류율 vs 디지털 트윈 예측값 (있을 경우 함께 플롯)
if qpu_exp_candidates and twin_exp_candidates:
    ax1.plot(N, df[qpu_exp_candidates[0]], 'o-', color='#D62728', linewidth=2, markersize=6, label='Real QPU (ibm_fez, Calibrated)')
    ax1.plot(N, df[twin_exp_candidates[0]], 's--', color='#1F77B4', linewidth=2, markersize=6, label='Digital Twin (Standard Noise)')
    ctrl_cols = [c for c in df.columns if 'qpu' in c.lower() and 'ctrl' in c.lower()]
    if ctrl_cols:
        ax1.plot(N, df[ctrl_cols[0]], '^:', color='#2CA02C', linewidth=1.8, markersize=6, label='QPU Unentangled Control')
    ax1.set_title('(a) Entangled GHZ Error Rate vs. Digital Twin', fontweight='bold')
    ax1.set_ylabel('Decoherence / Error Probability')
else:
    ax1.plot(N, residual, 'o-', color='#D62728', linewidth=2, label='Observed Residual')
    ax1.set_title('(a) Observed Residual Trajectory', fontweight='bold')
    ax1.set_ylabel('Residual Error')

ax1.set_xlabel('Entangled Qubit Count (N)')
ax1.grid(True, linestyle='--', alpha=0.4)
ax1.legend(frameon=True, fontsize=9.5)

# Panel B: 잔여 오차(Residual) 및 비선형 모델 피팅 곡선
n_smooth = np.linspace(min(N), max(N), 200)
ax2.scatter(N, residual, color='#111111', s=55, zorder=5, label='Observed Residual (QPU - Twin)')
ax2.axhline(0, color='gray', linestyle=':', linewidth=1.2)
ax2.plot(n_smooth, model_linear(n_smooth, *popt_lin), '--', color='#7F7F7F', linewidth=1.6, label=f'Linear Fit ($R^2$={r2_lin:.3f})')
ax2.plot(n_smooth, model_quad(n_smooth, *popt_quad), '-.', color='#FF7F0E', linewidth=1.8, label=f'Quadratic Crosstalk ($R^2$={r2_quad:.3f})')
if thr_fit_ok:
    ax2.plot(n_smooth, model_throttling(n_smooth, *popt_thr), '-', color='#9467BD', linewidth=2.4, label=f'Throttling Exp Model ($R^2$={r2_thr:.3f})')

ax2.set_title('(b) Excess Residual & Nonlinear Model Comparison', fontweight='bold')
ax2.set_xlabel('Entangled Qubit Count (N)')
ax2.set_ylabel('Excess Decoherence Residual')
ax2.grid(True, linestyle='--', alpha=0.4)
ax2.legend(frameon=True, fontsize=9.5)

plt.tight_layout()
out_fig = "phase4_residual_analysis_ibm_fez.png"
plt.savefig(out_fig, dpi=300)
print(f"\n[SUCCESS] 논문용 고해상도 그래프 저장 완료: {out_fig}")