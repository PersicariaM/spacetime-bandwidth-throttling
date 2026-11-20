import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

FEZ_CSV = "data/v3_raw_results_ibm_fez_dbvfn89cn7vc73egqiq0.csv"
KINGSTON_CSV = "data/v3_raw_results_ibm_kingston_dc011ueq4uuc73a1sk30.csv"
OUT_PNG = "paper/figures/v3_fig1_topology_inversion.png"
OUT_PDF = "paper/figures/v3_fig1_topology_inversion.pdf"

V2_MEAN = -0.0548
V2_STD = 0.0226

V3_STATS = {
    0: {"label": "0 Cycles\n(v2.0 1D Tree\nPooled)", "mean": -0.0548, "std": 0.0226,
        "annot": "6.36σ Suppression\n(p = 1.99e-10)", "color": "#1f77b4"},
    1: {"label": "1 Cycle\n(v3.0 kingston\n2D Patch)", "mean": 0.0046, "std": 0.0121,
        "annot": "Zero-Crossing\n(t = 1.07, p = 0.321)", "color": "#ff7f0e"},
    2: {"label": "2 Cycles\n(v3.0 fez\n2D Patch)", "mean": 0.0213, "std": 0.0194,
        "annot": "Sign Inversion\n(t = 3.10, p = 0.017*)", "color": "#d62728"},
}

def load_and_parse_csv(filepath: str, chip_name: str):
    if not os.path.exists(filepath):
        print(f"[경고] 파일을 찾을 수 없습니다: {filepath}")
        return None

    df = pd.read_csv(filepath)
    df["sim_err"] = 1.0 - df["mps_p0"]
    df["qpu_err"] = 1.0 - df["qpu_p0"]
    df["raw_res"] = df["qpu_err"] - df["sim_err"]  # = mps_p0 - qpu_p0

    modes = df["mode"].unique()
    if len(modes) >= 2:
        # bare / dd(cpmg) 모드가 분리된 경우 CZ 개수 기준으로 이중 차분 잔차 R(D) 계산
        piv = df.pivot(index="cz_count", columns="mode", values="raw_res").reset_index()
        dd_col = next((c for c in piv.columns if str(c).lower() not in ["cz_count", "bare", "base", "unmitigated"]), None)
        base_col = next((c for c in piv.columns if str(c).lower() in ["bare", "base", "unmitigated"]), None)
        if dd_col and base_col:
            piv["residual"] = piv[dd_col] - piv[base_col]
        else:
            piv["residual"] = piv.iloc[:, -1] - piv.iloc[:, 1]
        parsed = piv[["cz_count", "residual"]].rename(columns={"cz_count": "cz"})
    else:
        parsed = df[["cz_count", "raw_res"]].rename(columns={"cz_count": "cz", "raw_res": "residual"})

    parsed = parsed.dropna().sort_values("cz")
    print(f"[{chip_name}] 로드 완료 ({len(parsed)} points) | CZ: {parsed['cz'].min():.0f}~{parsed['cz'].max():.0f} | "
          f"mean = {parsed['residual'].mean():+.4f} ± {parsed['residual'].std(ddof=1):.4f}")
    return parsed

def main():
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    df_fez = load_and_parse_csv(FEZ_CSV, "ibm_fez (2 Cycles)")
    df_kingston = load_and_parse_csv(KINGSTON_CSV, "ibm_kingston (1 Cycle)")

    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Arial"],
        "axes.edgecolor": "#333333",
        "axes.linewidth": 0.9,
        "xtick.labelsize": 9.5,
        "ytick.labelsize": 9.5,
    })

    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(12.5, 5.2), dpi=300,
        gridspec_kw={"width_ratios": [1.05, 1.25]}
    )

    # Panel A: Closed Cycles (0 -> 1 -> 2)
    cycles = [0, 1, 2]
    means = [V3_STATS[c]["mean"] for c in cycles]
    stds = [V3_STATS[c]["std"] for c in cycles]
    colors = [V3_STATS[c]["color"] for c in cycles]
    labels = [V3_STATS[c]["label"] for c in cycles]

    ax1.axhspan(-0.10, 0.0, color="#e8f4f8", alpha=0.55, zorder=0)
    ax1.axhspan(0.0, 0.065, color="#fdecea", alpha=0.55, zorder=0)
    ax1.axhline(0.0, color="#222222", linestyle="--", linewidth=1.2, zorder=1)
    ax1.plot(cycles, means, color="#555555", linestyle=":", linewidth=1.6, zorder=2)

    for c, m, s, col in zip(cycles, means, stds, colors):
        ax1.errorbar(
            c, m, yerr=s, fmt="o", markersize=9, color=col,
            ecolor=col, elinewidth=2.0, capsize=6, capthick=1.8,
            markeredgecolor="white", markeredgewidth=1.0, zorder=4
        )

    offsets = [(0, -0.036), (0, -0.028), (0, 0.026)]
    for c, m, (dx, dy) in zip(cycles, means, offsets):
        va = "top" if dy < 0 else "bottom"
        ax1.text(
            c + dx, m + dy,
            f"{m:+.4f} ± {V3_STATS[c]['std']:.4f}\n{V3_STATS[c]['annot']}",
            ha="center", va=va, fontsize=8.3, fontweight="bold",
            color=V3_STATS[c]["color"],
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=V3_STATS[c]["color"], alpha=0.88, lw=0.8),
            zorder=5
        )

    ax1.text(-0.42, 0.056, "2D Crosstalk / Overhead Regime (+)", fontsize=8.2, color="#a61c1c", fontweight="bold")
    ax1.text(-0.42, -0.108, "Non-Markovian CPMG Suppression Regime (-)", fontsize=8.2, color="#125582", fontweight="bold")

    ax1.set_xticks(cycles)
    ax1.set_xticklabels(labels, fontsize=9.0, fontweight="bold")
    ax1.set_xlim(-0.5, 2.5)
    ax1.set_ylim(-0.115, 0.065)
    ax1.set_ylabel("Mean Residual Error (QPU − Markovian Twin)", fontsize=10.5, fontweight="bold")
    ax1.set_title("(a) Topological Sign Inversion by Closed Cycles", fontsize=11.5, fontweight="bold", pad=10)
    ax1.grid(axis="y", linestyle=":", alpha=0.45)

    # Panel B: CZ Gate Density vs. Residual
    ax2.axhline(0.0, color="#222222", linestyle="--", linewidth=1.2, label="Markovian Twin Baseline (0.0)")
    ax2.axhspan(
        V2_MEAN - V2_STD, V2_MEAN + V2_STD,
        color="#1f77b4", alpha=0.14, label=f"v2.0 1D Tree Band ({V2_MEAN:+.4f} ± {V2_STD:.4f})"
    )
    ax2.axhline(V2_MEAN, color="#1f77b4", linestyle="-.", linewidth=1.1, alpha=0.85)

    if df_kingston is not None:
        ax2.plot(
            df_kingston["cz"], df_kingston["residual"],
            marker="s", markersize=6.5, linewidth=1.8, color="#ff7f0e",
            markeredgecolor="white", markeredgewidth=0.7,
            label="ibm_kingston (N=24, 1 Cycle, CZ 36–258)"
        )
        z_k = np.polyfit(df_kingston["cz"], df_kingston["residual"], 1)
        ax2.plot(df_kingston["cz"], np.polyval(z_k, df_kingston["cz"]),
                 color="#ff7f0e", linestyle=":", linewidth=1.2, alpha=0.7)

    if df_fez is not None:
        ax2.plot(
            df_fez["cz"], df_fez["residual"],
            marker="D", markersize=6.5, linewidth=1.8, color="#d62728",
            markeredgecolor="white", markeredgewidth=0.7,
            label="ibm_fez (N=24, 2 Cycles, CZ 38–270)"
        )
        z_f = np.polyfit(df_fez["cz"], df_fez["residual"], 1)
        ax2.plot(df_fez["cz"], np.polyval(z_f, df_fez["cz"]),
                 color="#d62728", linestyle=":", linewidth=1.2, alpha=0.7)

    ax2.set_xlabel("2-Qubit Entangling Gate Count (CZ Gates in N=24 Patch)", fontsize=10.5, fontweight="bold")
    ax2.set_ylabel("Residual Error (QPU − Markovian Twin)", fontsize=10.5, fontweight="bold")
    ax2.set_title("(b) Cross-Chip Residual Scaling Under Local 2D Compression", fontsize=11.5, fontweight="bold", pad=10)
    ax2.set_ylim(-0.10, 0.065)
    ax2.grid(True, linestyle=":", alpha=0.45)
    ax2.legend(loc="lower right", fontsize=8.3, frameon=True, framealpha=0.92, edgecolor="#cccccc")

    fig.suptitle(
        "Phase v3.0: Topology-Induced Inversion of Non-Markovian CPMG Suppression on IBM Heron r2",
        fontsize=12.8, fontweight="bold", y=0.98
    )

    plt.tight_layout(rect=[0, 0.0, 1, 0.94])
    plt.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
    plt.savefig(OUT_PDF, bbox_inches="tight")
    print(f"[성공] 저장 완료: {OUT_PNG} / {OUT_PDF}")

if __name__ == "__main__":
    main()