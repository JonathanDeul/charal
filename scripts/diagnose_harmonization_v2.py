#!/usr/bin/env python3
"""Post-hoc error analysis of saved predictions; no fitting or model selection.

Input bins are fixed or estimated on 2013-2020 fitting data only. Target-based
presence classes are diagnostic descriptions, never new predictor features.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/research/harmonization_v2"
KEYS = ["date", "gy", "gx"]
METHODS = ["seasonal_ratio", "nb_gam_ca", "nb_gam_west", "nb_gam_west_adapted", "poisson_gam_ca", "boosted_correction_ca"]


def score(frame, name):
    y = frame.viirs_count.to_numpy()
    p = frame[name].to_numpy()
    error = p-y
    total = float(np.abs(error).sum())
    return {"n": len(frame), "reference_total": float(y.sum()), "predicted_total": float(p.sum()),
        "mae": float(np.abs(error).mean()), "absolute_error_total": total,
        "bias_per_cell": float(error.mean()), "signed_error_total": float(error.sum()),
        "wape": total/float(y.sum()) if y.sum() else None,
        "monthly_total_mae": float(pd.DataFrame({"date": frame.date.to_numpy(), "error": error}).groupby("date").error.sum().abs().mean())}


def groups(frame, column):
    return [{"group": str(label), "n": len(block), "cell_fraction": len(block)/len(frame),
        "reference_total": float(block.viirs_count.sum()),
        "reference_fraction": float(block.viirs_count.sum()/frame.viirs_count.sum()),
        "models": {m: score(block, m) for m in METHODS}}
        for label, block in frame.groupby(column, observed=True, sort=True) if len(block)]


def run():
    cells_path = OUT / "cells.csv.gz"
    data = pd.read_csv(cells_path, dtype={"ecoregion": str})
    data = data[data.state.eq("CA") & data.pair_complete & data.viirs_count.notna()].copy()
    inputs = {"cells.csv.gz": hashlib.sha256(cells_path.read_bytes()).hexdigest()}
    for method in METHODS:
        path = OUT / f"predictions_{method}.csv.gz"
        pred = pd.read_csv(path)[KEYS+["predicted"]].rename(columns={"predicted": method})
        data = data.merge(pred, on=KEYS, how="left", validate="one_to_one")
        inputs[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not np.isfinite(data[METHODS]).all().all():
        raise ValueError("Missing or nonfinite saved predictions")
    data["modis_bin"] = pd.cut(data.modis_count, [-1, 0, 4, 19, 99, 499, np.inf],
        labels=["0", "1–4", "5–19", "20–99", "100–499", "500+"])
    data["presence"] = np.select([
        data.modis_count.eq(0) & data.viirs_count.eq(0),
        data.modis_count.eq(0) & data.viirs_count.gt(0),
        data.modis_count.gt(0) & data.viirs_count.eq(0)],
        ["MODIS=0, VIIRS=0", "MODIS=0, VIIRS>0", "MODIS>0, VIIRS=0"], default="MODIS>0, VIIRS>0")
    data["region"] = np.where(data.latitude.ge(39.5), "North", "South")
    data["season"] = data.month.map({12:"DJF",1:"DJF",2:"DJF",3:"MAM",4:"MAM",5:"MAM",6:"JJA",7:"JJA",8:"JJA",9:"SON",10:"SON",11:"SON"})
    data["terra_fraction"] = data.terra_count/data.modis_count.clip(lower=1)
    data["terra_bin"] = pd.cut(data.terra_fraction, [-.01,0,.25,.75,.999999,1],
        labels=["Aqua only", "Terra up to 25%", "Mixed 25–75%", "Terra 75–100%", "Terra only"])
    data["day_bin"] = pd.cut(data.day_fraction, [-.01,0,.25,.75,.999999,1],
        labels=["Night only", "Day up to 25%", "Mixed 25–75%", "Day 75–100%", "Day only"])
    train_active = data[data.year.between(2013,2020) & data.modis_count.gt(0)]
    thresholds = {}
    for feature in ["frp_mean", "footprint_mean", "detection_days"]:
        cuts = np.unique(train_active[feature].quantile([.25,.5,.75]).to_numpy())
        thresholds[feature] = cuts.tolist()
        data[feature+"_bin"] = pd.cut(data[feature], [-np.inf,*cuts,np.inf]).astype(str)
    report = {"status": "Exploratory post-hoc diagnostic; no fitting, selection or production change.",
        "unit": "California state-clipped 0.5-degree cell-month, not individual fires or pixels",
        "splits": {}, "training_positive_modis_quartiles": thresholds, "input_sha256": inputs,
        "limits": ["2021-2022 is the previously inspected selection period; 2023-2025 is the known benchmark.",
            "Cell errors correlate in space/time. Tables are descriptive; no independent-sample confidence claims.",
            "Input strata overlap; their error totals must not be summed across different tables.",
            "VIIRS-only means positive retained reports in a cell-month with no retained MODIS reports, not necessarily a missed contemporaneous fire.",
            "No exposure masks are inputs. CSV zeros do not establish clear-sky observation.",
            "Quartile strata are marginal associations and can reflect count, region or season confounding.",
            "Group cell absolute errors do not add up to statewide monthly MAE because signed errors cancel before monthly scoring."]}
    for split, years in {"selection_2021_2022": (2021,2022), "known_benchmark_2023_2025": (2023,2025)}.items():
        f = data[data.year.between(*years)].copy()
        active = f[f.modis_count.gt(0)]
        result = {"overall": {m: score(f,m) for m in METHODS},
            "all_cells": {column: groups(f, column) for column in ["presence", "modis_bin", "region", "season", "month", "ecoregion"]},
            "positive_modis_only": {column: groups(active,column) for column in ["terra_bin", "day_bin", "frp_mean_bin", "footprint_mean_bin", "detection_days_bin"]}}
        # Joint input strata help distinguish a simple count effect from an
        # apparent seasonal or geographic association. No target-based bins here.
        f["region_count"] = f.region+" / MODIS "+f.modis_bin.astype(str)
        result["region_by_modis"] = groups(f,"region_count")
        zero = f[f.modis_count.eq(0)]
        result["zero_modis_by_ecoregion"] = groups(zero,"ecoregion")
        summary = []
        for method in METHODS:
            errors = f[method]-f.viirs_count
            top = f.assign(error=errors, abs_error=errors.abs()).nlargest(10,"abs_error")
            result.setdefault("largest_cell_errors",{})[method] = top[[*KEYS,"latitude","longitude","ecoregion","modis_count","viirs_count",method,"error"]].to_dict("records")
        # Exact additive decomposition of each statewide monthly signed error.
        for method in METHODS:
            for date, block in f.groupby("date"):
                no_modis = block.modis_count.eq(0)
                summary.append({"method":method,"date":date,
                    "zero_modis_signed_error":float((block.loc[no_modis,method]-block.loc[no_modis,"viirs_count"]).sum()),
                    "positive_modis_signed_error":float((block.loc[~no_modis,method]-block.loc[~no_modis,"viirs_count"]).sum()),
                    "total_signed_error":float((block[method]-block.viirs_count).sum())})
        result["monthly_error_decomposition"] = summary
        report["splits"][split] = result
    (OUT/"diagnostics.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    lines = ["# Input-conditioned error analysis — 15 November 2026", "",
        "Exploratory analysis of saved predictions; no retraining or change to the frozen model-selection rule. Primary candidate: pooled West Negative-Binomial GAM (`nb_gam_west`). Control: current seasonal-ratio calibration. All units below are California **cell-months**, not individual fires. Outage-flagged paired months are excluded.", ""]
    for split,result in report["splits"].items():
        overall=result["overall"]
        lines += [f"## {split}", "", f"{overall['seasonal_ratio']['n']:,} cell-months; {overall['seasonal_ratio']['reference_total']:,.0f} VIIRS reports.", "",
            "| Presence class | Cell-months | Fraction of cells | VIIRS reports | Fraction of VIIRS | Ratio MAE/cell | West NB MAE/cell | West NB predicted total |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for row in result["all_cells"]["presence"]:
            a,b=row["models"]["seasonal_ratio"],row["models"]["nb_gam_west"]
            lines.append(f"| {row['group']} | {row['n']:,} | {row['cell_fraction']:.1%} | {row['reference_total']:,.0f} | {row['reference_fraction']:.1%} | {a['mae']:.2f} | {b['mae']:.2f} | {b['predicted_total']:,.1f} |")
        lines += ["", "| MODIS reports per cell-month | Cell-months | VIIRS reports | Ratio MAE/cell | West NB MAE/cell | Ratio signed error | West NB signed error | Fraction of West NB absolute cell error |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for row in result["all_cells"]["modis_bin"]:
            a,b=row["models"]["seasonal_ratio"],row["models"]["nb_gam_west"]
            lines.append(f"| {row['group']} | {row['n']:,} | {row['reference_total']:,.0f} | {a['mae']:.2f} | {b['mae']:.2f} | {a['signed_error_total']:,.0f} | {b['signed_error_total']:,.0f} | {b['absolute_error_total']/overall['nb_gam_west']['absolute_error_total']:.1%} |")
        for column in ["region","season"]:
            lines += ["",f"### {column}","","| Group | Cell-months | Ratio MAE/cell | West NB MAE/cell | Ratio monthly-total MAE | West NB monthly-total MAE |","| --- | ---: | ---: | ---: | ---: | ---: |"]
            for row in result["all_cells"][column]:
                a,b=row["models"]["seasonal_ratio"],row["models"]["nb_gam_west"]
                lines.append(f"| {row['group']} | {row['n']:,} | {a['mae']:.2f} | {b['mae']:.2f} | {a['monthly_total_mae']:.2f} | {b['monthly_total_mae']:.2f} |")
        lines += ["", "### Other input associations (positive MODIS cells only)", "",
            "| Feature | Group | Cell-months | Ratio MAE/cell | West NB MAE/cell |", "| --- | --- | ---: | ---: | ---: |"]
        for feature,rows in result["positive_modis_only"].items():
            for row in rows:
                a,b=row["models"]["seasonal_ratio"],row["models"]["nb_gam_west"]
                lines.append(f"| {feature} | {row['group']} | {row['n']:,} | {a['mae']:.2f} | {b['mae']:.2f} |")
        lines.append("")
    lines += ["## Interpretation", "",
        "For zero MODIS counts, the ratio prediction is exactly zero. In the GAM the entire multiplicative term is also zero, so only `softplus(region_floor)` remains: within the same ecological region, **all zero-MODIS inputs get the same prediction**, regardless of month or state. This follows from the fitted architecture, not a thresholded fire/no-fire classifier. It cannot identify which of the many zero-MODIS cell-months contain VIIRS reports. Positive fractional expected counts are not literal recovered detections.", "",
        "The all-zero group can dominate row counts while high-activity groups dominate absolute error. Always compare cell frequency, VIIRS mass, and error contribution separately. A large percentage error in a near-zero group does not establish the cause of statewide monthly error. The JSON includes exact monthly signed-error decompositions and all six model variants, ecological-region and month tables, joint region/count strata and largest errors.", "",
        "These are post-hoc associations, not causal effects of FRP, platform or geometry. Higher-count fires naturally have larger absolute errors; marginal feature strata can reflect that. No outage or extreme month was removed on the basis of model error. See `data/research/harmonization_v2/diagnostics.json` for complete results, bin thresholds and input hashes.", ""]
    (ROOT/"docs/HARMONIZATION_DIAGNOSTICS.md").write_text("\n".join(lines))
    print("Saved diagnostics.json and docs/HARMONIZATION_DIAGNOSTICS.md")


if __name__ == "__main__":
    run()
