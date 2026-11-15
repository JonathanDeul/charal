#!/usr/bin/env python3
"""Write a compact, reviewable report from saved experiment results."""
from __future__ import annotations

import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/research/harmonization_v2"
NAMES = {"seasonal_ratio": "Seasonal ratio (control)", "nb_gam_ca": "NB GAM / California",
    "nb_gam_west": "NB GAM / pooled West", "nb_gam_west_adapted": "NB GAM / West with state adaptation",
    "poisson_gam_ca": "Poisson GAM / California", "boosted_correction_ca": "Boosted correction / California"}


def main():
    report = json.loads((OUT / "report.json").read_text())
    baseline = report["selection"]["seasonal_ratio"]
    manifest = report["manifest"]
    counts = {}
    for row in manifest["counts"]:
        counts[row["state"]] = counts.get(row["state"], 0)+row["retained"]
    lines = ["# Harmonization v2 — completed experiment, 15 November 2026", "",
        "Follow-up: [input-conditioned error diagnostics](HARMONIZATION_DIAGNOSTICS.md) examine zero-MODIS/positive-VIIRS cases, activity levels, season, region, FRP and detected-pixel geometry using saved predictions only.", "",
        "**The production calendar retains the seasonal-ratio calibration.** The lowest statewide selection MAE belongs to the pooled western-US Negative-Binomial GAM, but it fails the predeclared regional and cell-level safeguards. No new model is presented as a validated replacement.", "",
        "The California-only Poisson GAM and boosted correction improve the already-known 2023–2025 benchmark. Those scores do not override the frozen selection rule; the former performs worse in 2021–2022 and the latter worsens Northern California there.", "",
        "## Data and design", "",
        f"Reprocessed **{sum(counts.values()):,}** retained, real detections across CA, OR, WA, NV and AZ from the 39 existing complete US annual archives. No additional hotspot archive download was needed. Prepared **{manifest['cell_months']:,}** state-clipped cell-months across **{manifest['grid_rows']}** cells. Static EPA Level III regions are assigned by largest intersection within each state-clipped cell; angular intersection area is an approximation, not an equal-area ecological fraction.", "",
        "| State | Retained detections |", "| --- | ---: |",
        *[f"| {state} | {number:,} |" for state, number in sorted(counts.items())], "",
        "California monthly MODIS/VIIRS counts match the previous prepared snapshot. The v2 grid uses the accurate acquisition boundary, yielding 224 California cells versus 223 in the previous simplified display-boundary grid. The extra cell is empty in the evaluated years; cell-average metrics therefore have a slightly different denominator. Statewide totals and MAE remain directly comparable.", "",
        "- Development: train 2013–2016 → validate 2017–2018; train 2013–2018 → validate 2019–2020. These folds choose one of two predeclared GAM penalties.",
        "- Fit: 2013–2020. Candidate selection: 2021–2022 (20 eligible months), using California monthly total MAE only.",
        "- Benchmark: 2023–2025 (31 eligible months), **already inspected in the earlier experiment**, never used for v2 fitting/selection. The 2021–2022 selection-period scores were also visible previously; neither period is a newly untouched dataset.",
        "- Backward audit: February–December 2012, excluding independently flagged outage months (10 eligible months). Newly reserved for this experiment, not certified never inspected; earlier published artifacts already contain 2012.",
        "- Geographic audit: fit south of 39.5°N in all participating states and remove all cells within 0.5° (maximum-coordinate distance) of northern California audit cells. Evaluate northern CA in 2023–2025. This audit changes the fitting geography relative to v1.",
        "- Same vegetation/confidence filter and independently sourced NASA outage exclusions as v1. A zero is no retained reports, not verified fire-free or clear-sky exposure.", "",
        f"Frozen [protocol](../research/harmonization_v2/protocol.json) SHA-256: `{report['protocol_sha256']}`. Selection is saved before final audit predictions in `data/research/harmonization_v2/selection.json`. All targets remain SNPP 375m reported detections; other VIIRS satellites are never pooled into that target.", "",
        "## Architecture", "",
        "The GAM models `mean = seasonal_ratio_prediction × exp(spline_and_region_correction) + softplus(region_floor)`. The floor permits expected VIIRS reports in a cell with no MODIS reports. The correction uses log counts, FRP sum/mean/max/std, Terra fraction, day fraction, detected-pixel scan/track/footprint, circular UTC acquisition time, detection-day/acquisition counts, calendar month, and static ecological region. Knots, scaling, ratios and coefficients are fitted only on fitting rows. Spline corrections extrapolate constantly; the count baseline can still grow. A smooth saturation prevents numerical overflow.", "",
        "Region effects use Gaussian shrinkage via penalized maximum likelihood (MAP partial pooling); these are not sampled Bayesian posteriors. NB2 dispersion is fixed at 1 by the protocol; the Poisson control uses dispersion 0. The adapted West fit adds state effects and state/month baseline ratios and assigns 50% total fitting weight to CA and 50% to the other states combined. The plain West fit pools row weights equally. The boosted correction is shallow, regularized Poisson boosting with a baseline offset represented through exposure-weighted training.", "",
        "Year, VIIRS counts and VIIRS mask information are excluded from predictors. Detected-pixel geometry and acquisition features are explicitly **not** measures of total satellite exposure. No vegetation time series was acquired; EPA regions are a static ecological proxy.", "",
        "## Selection and audit results", "",
        "All MAE values below refer to reported detection counts per statewide month, except the explicitly northern spatial audit.", "",
        "| Method | Development mean MAE | Selection MAE | Known benchmark MAE | Known benchmark WAPE | 2012 backward MAE | Northern spatial MAE |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name in report["protocol"]["models"]:
        cv = next(row for row in report["development"][name] if row["penalty"] == report["selected_penalties"][name])
        s, t, b, g = [report[k][name] for k in ("selection", "benchmark", "backward_audit", "spatial_audit")]
        lines.append(f"| {NAMES[name]} | {cv['monthly_mae']:.2f} | {s['monthly_mae']:.2f} | {t['monthly_mae']:.2f} | {t['monthly_wape']:.2%} | {b['monthly_mae']:.2f} | {g['monthly_mae']:.2f} |")
    chosen = report["selection"][report["selected_candidate"]]
    lines += ["", "The frozen promotion gate requires at least 5% lower selection statewide MAE, with cell MAE and each north/south regional MAE no more than 5% worse. The raw selection winner is evaluated against this gate; a lower-ranked candidate is not substituted after inspecting audits.", "",
        "| Selection safeguard | Ratio control | Pooled West NB GAM | Outcome |", "| --- | ---: | ---: | --- |",
        f"| Statewide monthly MAE | {baseline['monthly_mae']:.2f} | {chosen['monthly_mae']:.2f} | {1-chosen['monthly_mae']/baseline['monthly_mae']:.1%} improvement |",
        f"| Cell-month MAE | {baseline['cell_month_mae']:.2f} | {chosen['cell_month_mae']:.2f} | fails |",
        *[f"| {r.title()} monthly MAE | {baseline['regions'][r]['monthly_mae']:.2f} | {chosen['regions'][r]['monthly_mae']:.2f} | fails |" for r in ("north", "south")], "",
        "This is evidence of aggregate error cancellation, not a robust spatial improvement. Extra western observations help this particular statewide selection score, but not California performance consistently across periods and regions. The geographic audit is particularly unfavorable for the GAMs. Baseline retention follows the protocol; it was not chosen after looking at the final benchmark.", "",
        "## Real observation-mask pilot", ""]
    for file, label in [("mask_pilot.json", "MODIS"), ("viirs_mask_pilot.json", "VIIRS")]:
        path = OUT / file
        if not path.exists():
            lines.append(f"{label}: no completed acquisition manifest yet.")
            continue
        mask = json.loads(path.read_text())
        lines.append(f"**{label}: {mask['status']}**. See `data/research/harmonization_v2/{file}` for granule URLs, byte counts and SHA-256 hashes.")
        if label == "MODIS":
            lines.append(f"Downloaded {sum(f['status']=='downloaded' for f in mask['files'])} Terra/Aqua MOD14A1/MYD14A1 Collection 6.1 tiles, covering eight daily masks starting 2018-07-20 and 2020-08-20. Aggregated {mask.get('cell_days', 0):,} product/cell/day records. Pixel-class totals partition the selected California pixels exactly. Small coastal grid slivers without a 1km pixel center are not converted to observed zeros.")
        elif mask["status"] == "acquired_and_geolocated":
            lines.append(f"Downloaded VNP14IMG Collection 2 and matched VNP03IMG geolocation for the 2020-08-20 19:36 UTC swath. Geolocated the full 375m mask to {mask['cells']} California cells. Cloud, bowtie, glint, unknown and fire classes remain distinguishable.")
        lines.append("")
    lines += ["These real masks establish a working acquisition/geolocation path. They are **not included as predictors in the hotspot-only full-period models**: sparse pilot coverage would otherwise create a missingness shortcut and would be unavailable for historical application. Daily MODIS maximum composites and a single VIIRS swath are not directly interchangeable exposure denominators. A subsequent exposure-aware experiment needs consistently matched mask coverage across fitting, validation and historical application periods; the pilot does not prove that such features improve calibration.", "",
        "## Artifacts and reproduction", "",
        "```sh", ".venv/bin/python -m pip install -r requirements-research.txt",
        ".venv/bin/python scripts/prepare_harmonization_v2.py",
        ".venv/bin/python scripts/train_harmonization_v2.py",
        ".venv/bin/python scripts/fetch_observation_mask_pilot.py",
        ".venv/bin/python scripts/fetch_viirs_mask_pilot.py",
        ".venv/bin/python scripts/report_harmonization_v2.py",
        ".venv/bin/python -m pytest tests -q", "```", "",
        "- Trained weights: `models/harmonization_v2/*.pkl` (trusted local artifacts only).",
        "- Full metrics, monthly residuals, convergence and split metadata: `data/research/harmonization_v2/report.json`.",
        "- Selection checkpoint, source hashes, prepared cells and per-cell predictions: `data/research/harmonization_v2/`.",
        "- Research runtime versions and source hashes: `research/harmonization_v2/environment.json`.",
        "- Production `models/harmonization.pkl`, `data/processed/analysis.json` and its compressed app payload are preserved. No deployment was performed.", "",
        "The scripts reuse cached public geography/archives. Mask downloads use the existing server-side `EARTHDATA_KEY` without printing it or saving it to manifests. Mask libraries are research-only dependencies. Missing whole sensor-years are rejected. JSON serialization rejects NaNs; unavailable regional metrics are null.", "",
        "## Interpretation limits", "",
        "Reported detections are neither independent fires nor burned area. Model superiority on these counts would not establish reconstruction of true fire activity. Orbit changes, inconsistent archived processing versions, unmeasured exposure, early Terra-only sampling and historical fire-regime shifts remain. Pre-2012 VIIRS backcasts cannot be directly validated. Neither the known benchmark nor the newly reserved backward audit is advertised as a pristine, never-inspected test.", "",
        "Sources: [NASA MODIS fire products](https://modis.gsfc.nasa.gov/data/dataprod/mod14.php/index.php), [NASA VIIRS products](https://viirsland.gsfc.nasa.gov/Products/NASA/FireESDR.html), [EPA ecological regions](https://www.epa.gov/eco-research/level-iii-and-iv-ecoregions-continental-united-states), [Census state geography](https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/State_County/MapServer/0).", ""]
    (ROOT / "docs/HARMONIZATION_V2.md").write_text("\n".join(lines))
    packages = ["numpy", "pandas", "scipy", "scikit-learn", "shapely", "pyhdf", "pyproj", "h5py"]
    source_files = ["backend/harmonization_v2.py", "scripts/prepare_harmonization_v2.py", "scripts/train_harmonization_v2.py",
                    "scripts/fetch_observation_mask_pilot.py", "scripts/fetch_viirs_mask_pilot.py", "research/harmonization_v2/protocol.json"]
    environment = {"python": platform.python_version(), "packages": {p: version(p) for p in packages},
        "source_sha256": {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in source_files}}
    (ROOT / "research/harmonization_v2/environment.json").write_text(json.dumps(environment, indent=2))
    print("Saved docs/HARMONIZATION_V2.md")


if __name__ == "__main__":
    main()
