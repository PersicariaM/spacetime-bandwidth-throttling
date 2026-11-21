import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from qiskit_ibm_runtime import QiskitRuntimeService


def summarize_backend(service: QiskitRuntimeService, name: str) -> dict:
    backend = service.backend(name)
    target = backend.target
    props = backend.properties()

    t1_us, t2_us, ro_err, cz_err = [], [], [], []
    last_cal = None

    if props is not None:
        if getattr(props, "last_update_date", None):
            last_cal = str(props.last_update_date)
        for q in range(backend.num_qubits):
            try:
                v_t1 = props.t1(q)
                if v_t1 is not None:
                    t1_us.append(v_t1 * 1e6)
            except Exception:
                pass
            try:
                v_t2 = props.t2(q)
                if v_t2 is not None:
                    t2_us.append(v_t2 * 1e6)
            except Exception:
                pass
            try:
                v_ro = props.readout_error(q)
                if v_ro is not None:
                    ro_err.append(v_ro)
            except Exception:
                pass

    if "cz" in target:
        for qargs, inst_props in target["cz"].items():
            if inst_props is not None and inst_props.error is not None:
                cz_err.append(float(inst_props.error))

    def stats(arr):
        if not arr:
            return None
        a = np.array(arr, dtype=float)
        return {
            "count": int(len(a)),
            "median": round(float(np.median(a)), 6),
            "mean": round(float(np.mean(a)), 6),
            "std": round(float(np.std(a)), 6),
            "min": round(float(np.min(a)), 6),
            "max": round(float(np.max(a)), 6),
        }

    return {
        "backend": name,
        "num_qubits": backend.num_qubits,
        "last_calibration_update": last_cal,
        "t1_us": stats(t1_us),
        "t2_us": stats(t2_us),
        "readout_error": stats(ro_err),
        "cz_error": stats(cz_err),
    }


def main():
    service = QiskitRuntimeService()
    backends = ["ibm_fez", "ibm_kingston", "ibm_marrakesh"]
    captured_at = datetime.now(timezone.utc).isoformat()
    summaries = []

    print(f"=== IBM Heron r2 Calibration Snapshot ({captured_at}) ===")
    for bname in backends:
        info = summarize_backend(service, bname)
        summaries.append(info)
        print(
            f"[{bname}] last_cal={info['last_calibration_update']} | "
            f"T1_med={info['t1_us']['median']:.1f}us | "
            f"T2_med={info['t2_us']['median']:.1f}us | "
            f"CZ_med={info['cz_error']['median']:.5f} | "
            f"RO_med={info['readout_error']['median']:.5f}"
        )

    Path("data").mkdir(exist_ok=True)
    out_path = Path("data/ibm_heron_r2_calibration_snapshot.json")
    out_path.write_text(
        json.dumps({"captured_at_utc": captured_at, "backends": summaries}, indent=2),
        encoding="utf-8",
    )
    print(f"\n[완료] 저장됨: {out_path}")


if __name__ == "__main__":
    main()
