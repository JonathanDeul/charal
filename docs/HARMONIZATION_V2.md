# Harmonization v2 — completed experiment, 15 November 2026

Follow-up: [input-conditioned error diagnostics](HARMONIZATION_DIAGNOSTICS.md) examine zero-MODIS/positive-VIIRS cases, activity levels, season, region, FRP and detected-pixel geometry using saved predictions only.

**The production calendar retains the seasonal-ratio calibration.** The lowest statewide selection MAE belongs to the pooled western-US Negative-Binomial GAM, but it fails the predeclared regional and cell-level safeguards. No new model is presented as a validated replacement.

The California-only Poisson GAM and boosted correction improve the already-known 2023–2025 benchmark. Those scores do not override the frozen selection rule; the former performs worse in 2021–2022 and the latter worsens Northern California there.

## Data and design

Reprocessed **2,365,587** retained, real detections across CA, OR, WA, NV and AZ from the 39 existing complete US annual archives. No additional hotspot archive download was needed. Prepared **230,400** state-clipped cell-months across **768** cells. Static EPA Level III regions are assigned by largest intersection within each state-clipped cell; angular intersection area is an approximation, not an equal-area ecological fraction.

| State | Retained detections |
| --- | ---: |
| AZ | 212,972 |
| CA | 1,169,069 |
| NV | 77,432 |
| OR | 533,736 |
| WA | 372,378 |

California monthly MODIS/VIIRS counts match the previous prepared snapshot. The v2 grid uses the accurate acquisition boundary, yielding 224 California cells versus 223 in the previous simplified display-boundary grid. The extra cell is empty in the evaluated years; cell-average metrics therefore have a slightly different denominator. Statewide totals and MAE remain directly comparable.

- Development: train 2013–2016 → validate 2017–2018; train 2013–2018 → validate 2019–2020. These folds choose one of two predeclared GAM penalties.
- Fit: 2013–2020. Candidate selection: 2021–2022 (20 eligible months), using California monthly total MAE only.
- Benchmark: 2023–2025 (31 eligible months), **already inspected in the earlier experiment**, never used for v2 fitting/selection. The 2021–2022 selection-period scores were also visible previously; neither period is a newly untouched dataset.
- Backward audit: February–December 2012, excluding independently flagged outage months (10 eligible months). Newly reserved for this experiment, not certified never inspected; earlier published artifacts already contain 2012.
- Geographic audit: fit south of 39.5°N in all participating states and remove all cells within 0.5° (maximum-coordinate distance) of northern California audit cells. Evaluate northern CA in 2023–2025. This audit changes the fitting geography relative to v1.
- Same vegetation/confidence filter and independently sourced NASA outage exclusions as v1. A zero is no retained reports, not verified fire-free or clear-sky exposure.

Frozen [protocol](../research/harmonization_v2/protocol.json) SHA-256: `8933a69555b5982c1c9a13c371fef8f39e575ce8d0789dd6d9bd6ec73665280d`. Selection is saved before final audit predictions in `data/research/harmonization_v2/selection.json`. All targets remain SNPP 375m reported detections; other VIIRS satellites are never pooled into that target.

## Architecture

The GAM models `mean = seasonal_ratio_prediction × exp(spline_and_region_correction) + softplus(region_floor)`. The floor permits expected VIIRS reports in a cell with no MODIS reports. The correction uses log counts, FRP sum/mean/max/std, Terra fraction, day fraction, detected-pixel scan/track/footprint, circular UTC acquisition time, detection-day/acquisition counts, calendar month, and static ecological region. Knots, scaling, ratios and coefficients are fitted only on fitting rows. Spline corrections extrapolate constantly; the count baseline can still grow. A smooth saturation prevents numerical overflow.

Region effects use Gaussian shrinkage via penalized maximum likelihood (MAP partial pooling); these are not sampled Bayesian posteriors. NB2 dispersion is fixed at 1 by the protocol; the Poisson control uses dispersion 0. The adapted West fit adds state effects and state/month baseline ratios and assigns 50% total fitting weight to CA and 50% to the other states combined. The plain West fit pools row weights equally. The boosted correction is shallow, regularized Poisson boosting with a baseline offset represented through exposure-weighted training.

Year, VIIRS counts and VIIRS mask information are excluded from predictors. Detected-pixel geometry and acquisition features are explicitly **not** measures of total satellite exposure. No vegetation time series was acquired; EPA regions are a static ecological proxy.

## Selection and audit results

All MAE values below refer to reported detection counts per statewide month, except the explicitly northern spatial audit.

| Method | Development mean MAE | Selection MAE | Known benchmark MAE | Known benchmark WAPE | 2012 backward MAE | Northern spatial MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Seasonal ratio (control) | 932.67 | 730.71 | 291.33 | 13.21% | 204.77 | 106.74 |
| NB GAM / California | 1255.56 | 789.39 | 315.16 | 14.29% | 420.18 | 222.16 |
| NB GAM / pooled West | 1036.68 | 673.06 | 322.35 | 14.61% | 337.04 | 170.39 |
| NB GAM / West with state adaptation | 1068.92 | 750.86 | 294.36 | 13.34% | 402.10 | 173.32 |
| Poisson GAM / California | 767.20 | 874.22 | 240.17 | 10.89% | 114.06 | 207.93 |
| Boosted correction / California | 942.77 | 685.98 | 247.35 | 11.21% | 138.93 | 99.93 |

The frozen promotion gate requires at least 5% lower selection statewide MAE, with cell MAE and each north/south regional MAE no more than 5% worse. The raw selection winner is evaluated against this gate; a lower-ranked candidate is not substituted after inspecting audits.

| Selection safeguard | Ratio control | Pooled West NB GAM | Outcome |
| --- | ---: | ---: | --- |
| Statewide monthly MAE | 730.71 | 673.06 | 7.9% improvement |
| Cell-month MAE | 7.67 | 8.67 | fails |
| North monthly MAE | 358.69 | 443.30 | fails |
| South monthly MAE | 394.97 | 477.10 | fails |

This is evidence of aggregate error cancellation, not a robust spatial improvement. Extra western observations help this particular statewide selection score, but not California performance consistently across periods and regions. The geographic audit is particularly unfavorable for the GAMs. Baseline retention follows the protocol; it was not chosen after looking at the final benchmark.

## Real observation-mask pilot

**MODIS: acquired**. See `data/research/harmonization_v2/mask_pilot.json` for granule URLs, byte counts and SHA-256 hashes.
Downloaded 16 Terra/Aqua MOD14A1/MYD14A1 Collection 6.1 tiles, covering eight daily masks starting 2018-07-20 and 2020-08-20. Aggregated 7,072 product/cell/day records. Pixel-class totals partition the selected California pixels exactly. Small coastal grid slivers without a 1km pixel center are not converted to observed zeros.

**VIIRS: acquired_and_geolocated**. See `data/research/harmonization_v2/viirs_mask_pilot.json` for granule URLs, byte counts and SHA-256 hashes.
Downloaded VNP14IMG Collection 2 and matched VNP03IMG geolocation for the 2020-08-20 19:36 UTC swath. Geolocated the full 375m mask to 20 California cells. Cloud, bowtie, glint, unknown and fire classes remain distinguishable.

These real masks establish a working acquisition/geolocation path. They are **not included as predictors in the hotspot-only full-period models**: sparse pilot coverage would otherwise create a missingness shortcut and would be unavailable for historical application. Daily MODIS maximum composites and a single VIIRS swath are not directly interchangeable exposure denominators. A subsequent exposure-aware experiment needs consistently matched mask coverage across fitting, validation and historical application periods; the pilot does not prove that such features improve calibration.

## Artifacts and reproduction

```sh
.venv/bin/python -m pip install -r requirements-research.txt
.venv/bin/python scripts/prepare_harmonization_v2.py
.venv/bin/python scripts/train_harmonization_v2.py
.venv/bin/python scripts/fetch_observation_mask_pilot.py
.venv/bin/python scripts/fetch_viirs_mask_pilot.py
.venv/bin/python scripts/report_harmonization_v2.py
.venv/bin/python -m pytest tests -q
```

- Trained weights: `models/harmonization_v2/*.pkl` (trusted local artifacts only).
- Full metrics, monthly residuals, convergence and split metadata: `data/research/harmonization_v2/report.json`.
- Selection checkpoint, source hashes, prepared cells and per-cell predictions: `data/research/harmonization_v2/`.
- Research runtime versions and source hashes: `research/harmonization_v2/environment.json`.
- Production `models/harmonization.pkl`, `data/processed/analysis.json` and its compressed app payload are preserved. No deployment was performed.

The scripts reuse cached public geography/archives. Mask downloads use the existing server-side `EARTHDATA_KEY` without printing it or saving it to manifests. Mask libraries are research-only dependencies. Missing whole sensor-years are rejected. JSON serialization rejects NaNs; unavailable regional metrics are null.

## Interpretation limits

Reported detections are neither independent fires nor burned area. Model superiority on these counts would not establish reconstruction of true fire activity. Orbit changes, inconsistent archived processing versions, unmeasured exposure, early Terra-only sampling and historical fire-regime shifts remain. Pre-2012 VIIRS backcasts cannot be directly validated. Neither the known benchmark nor the newly reserved backward audit is advertised as a pristine, never-inspected test.

Sources: [NASA MODIS fire products](https://modis.gsfc.nasa.gov/data/dataprod/mod14.php/index.php), [NASA VIIRS products](https://viirsland.gsfc.nasa.gov/Products/NASA/FireESDR.html), [EPA ecological regions](https://www.epa.gov/eco-research/level-iii-and-iv-ecoregions-continental-united-states), [Census state geography](https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/State_County/MapServer/0).
