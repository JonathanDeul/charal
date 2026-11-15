#!/usr/bin/env python3
"""Run the frozen protocol; preserve v1 and write a separate research artifact."""
from __future__ import annotations

import hashlib
import json
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
from pathlib import Path
import pickle
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.harmonization_v2 import fitting_rows, make_model, metrics

OUT = ROOT / "data/research/harmonization_v2"
PROTOCOL = ROOT / "research/harmonization_v2/protocol.json"


def subset(frame, years):
    return frame[frame.year.between(*years) & frame.pair_complete & frame.viirs_count.notna()]


def diagnostics(frame, prediction):
    result = metrics(frame, prediction)
    result["regions"] = {name: metrics(frame[mask], prediction[mask.to_numpy()]) if mask.any() else None
        for name, mask in {"north": frame.latitude.ge(39.5), "south": frame.latitude.lt(39.5)}.items()}
    monthly = pd.DataFrame({"date": frame.date.to_numpy(), "actual": frame.viirs_count.to_numpy(), "predicted": prediction}).groupby("date").sum()
    result["monthly"] = monthly.reset_index().to_dict(orient="records")
    # Descriptive diagnostic, never used to filter or tune test observations.
    extreme = monthly.nlargest(min(3, len(monthly)), "actual")
    result["largest_three_reference_months_mae"] = float((extreme.predicted-extreme.actual).abs().mean())
    return result


def run():
    protocol_bytes = PROTOCOL.read_bytes()
    protocol = json.loads(protocol_bytes)
    report = {"protocol": protocol, "protocol_sha256": hashlib.sha256(protocol_bytes).hexdigest(),
        "started_at": datetime.now(timezone.utc).isoformat(), "manifest": json.loads((OUT / "manifest.json").read_text()),
        "development": {}, "selection": {}, "benchmark": {}, "backward_audit": {}, "spatial_audit": {}}
    frame = pd.read_csv(OUT / "cells.csv.gz", dtype={"ecoregion": str})
    ca = frame[frame.state.eq("CA")]
    penalties = {}
    for name in protocol["models"]:
        scores = []
        for penalty in protocol["gam_penalties"] if "gam" in name else [.1]:
            folds = []
            for spec in protocol["development_folds"]:
                train = fitting_rows(subset(frame, spec["train"]), name)
                valid = subset(ca, spec["validate"])
                model = make_model(name, penalty).fit(train)
                score = metrics(valid, model.predict(valid))
                folds.append({"spec": spec, "metrics": score, "optimization": getattr(model, "optimization", None)})
            score = float(np.mean([f["metrics"]["monthly_mae"] for f in folds]))
            scores.append({"penalty": penalty, "monthly_mae": score, "folds": folds})
            print("development", name, penalty, round(score, 2), flush=True)
        best = min(scores, key=lambda r: r["monthly_mae"])
        penalties[name] = best["penalty"]
        report["development"][name] = scores
    train = subset(frame, protocol["fit_years"])
    valid = subset(ca, protocol["selection_years"])
    models = {}
    for name in protocol["models"]:
        model = make_model(name, penalties[name]).fit(fitting_rows(train, name))
        models[name] = model
        report["selection"][name] = diagnostics(valid, model.predict(valid))
        report["selection"][name]["optimization"] = getattr(model, "optimization", None)
        print("selection", name, round(report["selection"][name]["monthly_mae"], 2), flush=True)
    selected = min(protocol["models"], key=lambda n: report["selection"][n]["monthly_mae"])
    baseline, candidate = report["selection"]["seasonal_ratio"], report["selection"][selected]
    gate = {"statewide_improvement_5pct": candidate["monthly_mae"] <= .95*baseline["monthly_mae"],
        "cell_no_more_than_5pct_worse": candidate["cell_month_mae"] <= 1.05*baseline["cell_month_mae"],
        "regions_no_more_than_5pct_worse": all(candidate["regions"][r]["monthly_mae"] <= 1.05*baseline["regions"][r]["monthly_mae"] for r in ("north", "south"))}
    report.update({"selected_candidate": selected, "promotion_gate": gate, "production_method": selected if all(gate.values()) else "seasonal_ratio", "selected_penalties": penalties})
    # Persist selection before any final audit predictions are computed.
    (OUT / "selection.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    modeldir = ROOT / "models/harmonization_v2"
    modeldir.mkdir(parents=True, exist_ok=True)
    test = subset(ca, protocol["known_benchmark_years"])
    backward = subset(ca, [2012, 2012])
    monthly_predictions = []
    for name, model in models.items():
        with (modeldir / f"{name}.pkl").open("wb") as f:
            pickle.dump(model, f)
        report["benchmark"][name] = diagnostics(test, model.predict(test))
        report["backward_audit"][name] = diagnostics(backward, model.predict(backward))
        south = fitting_rows(train[train.latitude.lt(39.5)], name)
        north = test[test.latitude.ge(39.5)]
        # Remove geographically adjacent cells across state borders as well.
        # Latitude <39.5 already leaves 0.5 degree separation between centers;
        # require >0.5 separation from every spatial audit cell.
        audit_locations = north[["latitude", "longitude"]].drop_duplicates().to_numpy()
        locations = south[["latitude", "longitude"]].to_numpy()
        distance = np.max(np.abs(locations[:, None, :]-audit_locations[None, :, :]), axis=2).min(axis=1)
        south = south[distance > .5]
        spatial = make_model(name, penalties[name]).fit(south)
        report["spatial_audit"][name] = diagnostics(north, spatial.predict(north))
        prediction = model.predict(ca)
        historical = ca[["date", "year", "month", "gy", "gx", "latitude", "longitude", "modis_count", "viirs_count"]].copy()
        historical["predicted"] = prediction
        # Exploratory only; do not turn unavailable months into display values.
        historical.to_csv(OUT / f"predictions_{name}.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
        monthly = historical.groupby("date")[["modis_count", "viirs_count", "predicted"]].sum(min_count=1).reset_index()
        monthly["method"] = name
        monthly_predictions.append(monthly)
        print("audits", name, "known WAPE", round(report["benchmark"][name]["monthly_wape"], 4), flush=True)
    pd.concat(monthly_predictions, ignore_index=True).to_csv(OUT / "monthly_predictions.csv", index=False)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["limits"] = ["2023-2025 benchmark was already inspected before this experiment; it is not a new independent test.",
        "2012 is newly reserved for this protocol, not certified never inspected, and has a different platform/algorithm regime.",
        "2013-2020 development years are reused for final fitting; only 2021-2022 selects the candidate.",
        "Static ecological regions and detection-conditioned geometry do not quantify actual observing exposure.",
        "Historical backcasts before VIIRS cannot be directly validated against VIIRS.",
        "No production files changed by this training script. Promotion is a separate deterministic export gated on selection metrics."]
    (OUT / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    print("Complete. Selected:", selected, "production:", report["production_method"], flush=True)


if __name__ == "__main__":
    run()
