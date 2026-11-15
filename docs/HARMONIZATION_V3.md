# Daily spatial/temporal context experiment — 15 November 2026

**Selection winner: Boosting / context.** Selection statewide monthly MAE: 769.03, versus 841.46 for the seasonal control fitted on the identical purged daily training rows. This is an exploratory follow-up; production was not changed.

## Design and data

All seven methods predict daily SNPP VIIRS counts in the same 224 California state-clipped 0.5° cells. Daily predictions are summed to calendar months for the primary metric. Input center values match the California-clipped archive exactly. Context contains MODIS from the five-state western union, using seven days (−3 through +3) and a 5×5 cell patch. At this coarse resolution the patch spans 2.5°; it is a regional context experiment, not precise fire-front reconstruction.

Four input channels: Terra count, Aqua count, FRP sum, and daytime count. The fifth channel marks source/domain/split availability, **not** cloud-free observation. Inputs are fixed log1p transforms. Both architectures also receive fixed cell coordinates, ecological-region indicators and calendar-month sine/cosine. No year, VIIRS values, CAL FIRE values or observation-mask pilot data are input features.

Boosting with context receives the flattened **same full patch** as the CNN; no neighborhood information is withheld from it. The point controls receive the same central-day channels and static features. The contextual CNN has one 8-filter 3×3 spatial convolution over the 35 day/channel planes, followed by a 24-unit hidden layer. This is a compact first configuration, not an exhaustive neural-network search. The point network is a small MLP. The neural count mean is a seasonal-ratio signal times a learned correction plus a context-dependent positive additive term.

- Development fit: 2013–2018; epoch choice: 2019–2020 from 2, 4, 8 epochs.
- Final fit: 2013–2020; family selection: 2021–2022.
- Known benchmark: 2023–2025; backward audit: February–December 2012, eligible months only.
- All evaluated target months pass the original independently sourced MODIS/SNPP outage policy. All days in those months are evaluated, including double-zero days.
- Source context cannot cross the split-year boundaries. The +3-day context makes this a **retrospective reconstruction**, not a real-time predictor.
- All periods have been inspected in previous work; this follow-up does not manufacture a pristine independent test.

Daily archive: 1,145,536 California cell-days across 2012–2025. Every full reference month's central MODIS and VIIRS totals were checked against v2. Development training retains 465,457 rows after purging 18,831; final training retains 616,674 after purging 31,358.

For stochastic/boosted fitting, all rows with local MODIS>0 or VIIRS>0 plus a seeded 10% sample of double-zero rows are used, with inverse-probability weights. This gives 67,075 development and 90,992 final fitting examples. Boosting and neural families share this sample; the common ratio anchor is estimated on all remaining fitting rows. Evaluation is completely unsampled. The aggregate-loss variant additionally optimizes full training-month north/south log-total disagreement with weight 0.1, using all remaining rows after event purging and without negative sampling; this entails extra optimizer steps and is not a compute-matched loss-only comparison.

## CAL FIRE use and boundary guard

CAL FIRE is used **only for split protection and descriptive evaluation**. Records are connected by normalized IRWIN and complex IDs; there are 8,249 linked groups. Final geometry/area are never provided to a predictor or substituted for VIIRS labels. Final fitting excludes spatial/temporal input supports associated with 17 known linked groups touching a later audit period. The spatial guard expands by the context radius; the temporal guard expands by three days.

Unknown start/end dates fall back conservatively to the source year bounds. Missing linkage metadata, unreported fires and coarse final geometries prevent a guarantee of event independence. The large-event diagnostic selects cell-days intersecting final reported perimeters during their reported alarm-to-containment interval, with maximum linked-record area ≥10,000 ha. It is not a daily burned-area truth or an independent sample of fires.

## Main results

MAE below is the absolute error of the statewide **monthly total**, in reported detections. WAPE divides summed absolute monthly errors by summed reference counts.

| Method | Selection 2021–22 MAE | Known 2023–25 MAE | Known 2023–25 WAPE | Backward 2012 MAE |
| --- | ---: | ---: | ---: | ---: |
| Seasonal ratio (same purged fitting rows) | 841.46 | 317.68 | 14.40% | 164.96 |
| Boosting / no context | 893.90 | 289.67 | 13.13% | 403.92 |
| Boosting / context | 769.03 | 264.37 | 11.98% | 249.22 |
| MLP / no context / Poisson | 913.32 | 307.54 | 13.94% | 313.22 |
| CNN / context / Poisson | 918.82 | 339.49 | 15.39% | 288.33 |
| CNN / context / learned NB dispersion | 4916.03 | 537.14 | 24.35% | 834.35 |
| CNN / context / Poisson + regional monthly loss | 982.50 | 348.39 | 15.79% | 220.44 |

For reference, the **unchanged deployed v1 ratio** has selection MAE 730.71 and known-benchmark MAE 291.33. V3's ratio is refitted after the new event guard; differences between these controls must not be attributed to context or a neural architecture.

### Context comparisons

| Comparison | Selection MAE change with context | Known benchmark MAE change with context |
| --- | ---: | ---: |
| Boosting: point → full patch | +14.0% | +8.7% |
| Neural: point MLP → patch CNN, Poisson | -0.6% | -10.4% |

The event guard removes 4.8% of training cell-days, but 31.0% of training VIIRS reports and 27.5% of MODIS reports. Event removal can therefore substantially shift the activity distribution. Comparing v3 directly with v1 combines an architecture/input change with a training-data change; the within-v3 controls are the fair architectural comparison.


Positive percentages mean lower error with context. The neural comparison changes architecture along with input support; the boosting comparison isolates adding the patch to the same estimator settings. Agreement or disagreement across these comparisons is more informative than a single winner.

### Regional and local safeguards

| Method | Selection north monthly MAE | Selection south monthly MAE | Selection cell-month MAE | Known cell-month MAE |
| --- | ---: | ---: | ---: | ---: |
| Seasonal ratio (same purged fitting rows) | 403.12 | 459.76 | 7.88 | 3.98 |
| Boosting / no context | 536.51 | 436.91 | 8.81 | 4.15 |
| Boosting / context | 456.00 | 359.41 | 8.54 | 3.65 |
| MLP / no context / Poisson | 410.53 | 559.98 | 9.79 | 4.31 |
| CNN / context / Poisson | 486.07 | 483.74 | 8.61 | 4.17 |
| CNN / context / learned NB dispersion | 3742.65 | 1212.82 | 24.78 | 4.75 |
| CNN / context / Poisson + regional monthly loss | 509.47 | 502.20 | 8.15 | 4.02 |

### Zero-MODIS and high-activity diagnostics: selection

| Method | Zero-MODIS day MAE | Zero-MODIS month MAE | ≥500 MODIS/month MAE | ≥500 MODIS/month signed bias | Large-event daily MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| Seasonal ratio (same purged fitting rows) | 0.081 | 0.78 | 679.45 | -4.1% | 19.369 |
| Boosting / no context | 0.134 | 1.34 | 770.34 | -9.2% | 17.901 |
| Boosting / context | 0.129 | 1.12 | 782.05 | -3.6% | 16.302 |
| MLP / no context / Poisson | 0.137 | 1.53 | 912.70 | -5.2% | 19.410 |
| CNN / context / Poisson | 0.143 | 1.62 | 704.89 | +0.4% | 19.205 |
| CNN / context / learned NB dispersion | 0.125 | 1.10 | 3238.86 | +55.4% | 35.476 |
| CNN / context / Poisson + regional monthly loss | 0.106 | 1.19 | 702.01 | +0.8% | 19.900 |

High-activity group: 27 cell-months. Negative bias indicates underprediction of the group's total; it can conceal large individual over/under errors. Daily-zero and month-zero strata differ: a month can have positive MODIS totals while many individual days have none. Large-event stratum: 3,255 cell-days.


### Zero-MODIS and high-activity diagnostics: known_benchmark

| Method | Zero-MODIS day MAE | Zero-MODIS month MAE | ≥500 MODIS/month MAE | ≥500 MODIS/month signed bias | Large-event daily MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| Seasonal ratio (same purged fitting rows) | 0.078 | 0.95 | 586.98 | +9.3% | 6.621 |
| Boosting / no context | 0.133 | 1.48 | 419.07 | +1.5% | 6.177 |
| Boosting / context | 0.124 | 1.23 | 431.64 | +9.9% | 5.806 |
| MLP / no context / Poisson | 0.134 | 1.61 | 321.36 | +2.2% | 6.376 |
| CNN / context / Poisson | 0.127 | 1.50 | 591.67 | +16.1% | 6.664 |
| CNN / context / learned NB dispersion | 0.118 | 1.20 | 1823.48 | +59.3% | 9.003 |
| CNN / context / Poisson + regional monthly loss | 0.102 | 1.32 | 601.67 | +14.9% | 6.730 |

High-activity group: 4 cell-months. Negative bias indicates underprediction of the group's total; it can conceal large individual over/under errors. Daily-zero and month-zero strata differ: a month can have positive MODIS totals while many individual days have none. Large-event stratum: 1,507 cell-days.

## Distinguishing VIIRS-only activity from truly empty cell-months

This target-conditioned diagnostic is descriptive only. No VIIRS presence is used as an inference feature.

| Period | Group (MODIS=0) | Cell-months | Actual VIIRS | Boost point predicted | Boost context predicted | Boost point MAE | Boost context MAE |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| selection | Both zero | 2,493 | 0 | 2,672 | 2,044 | 1.07 | 0.82 |
| selection | VIIRS positive | 817 | 2,598 | 2,056 | 1,468 | 2.15 | 2.04 |
| known_benchmark | Both zero | 3,872 | 0 | 4,428 | 3,182 | 1.14 | 0.82 |
| known_benchmark | VIIRS positive | 1,384 | 5,003 | 3,589 | 2,488 | 2.41 | 2.38 |

A lower predicted total is not automatically worse: a model can reduce erroneous positive expectations at the wrong locations. Compare absolute error in VIIRS-positive and genuinely empty groups separately. The seasonal ratio always predicts zero in both groups, so it sacrifices VIIRS-only activity but incurs no error in the much larger truly empty group. Context improves both groups relative to point boosting here, while the combined zero-MODIS MAE can still be worse than the ratio control.

## Seed stability and training

| Neural family | Chosen epochs | Selection monthly MAE by seed 42 / 43 / 44 | Ensemble selection MAE |
| --- | ---: | --- | ---: |
| MLP / no context / Poisson | 8 | 935.0 / 885.3 / 919.7 | 913.3 |
| CNN / context / Poisson | 4 | 1035.6 / 920.7 / 979.6 | 918.8 |
| CNN / context / learned NB dispersion | 8 | 3794.5 / 5012.6 / 5987.1 | 4916.0 |
| CNN / context / Poisson + regional monthly loss | 2 | 1084.4 / 956.7 / 935.0 | 982.5 |

Learned global NB2 dispersion by seed: 0.4030, 0.4035, 0.4039. Seed variation measures optimizer sensitivity, not independent-data confidence intervals. Main experiment runtime: 16.2 minutes on CPU with four Torch threads. No test-time fitting or calibration was performed.

## Spatial transfer diagnostic

Refit on 129 California cells whose centers are more than 2° (maximum-coordinate distance) from every northern audit cell. This separates full 5×5 input patches geographically. Fit 2013–2020; evaluate northern California in 2023–2025. Training rows: 353,125; audit rows: 51,920. Neural epochs are reused from the main development stage, which included northern CA in earlier years: this is a fixed-configuration transfer check, not wholly unseen-geography model development.

| Method | Northern transfer monthly MAE | Northern transfer WAPE |
| --- | ---: | ---: |
| Seasonal ratio (same purged fitting rows) | 141.32 | 15.61% |
| Boosting / no context | 479.47 | 52.96% |
| Boosting / context | 159.36 | 17.60% |
| MLP / no context / Poisson | 161.18 | 17.80% |
| CNN / context / Poisson | 138.15 | 15.26% |
| CNN / context / learned NB dispersion | 160.35 | 17.71% |
| CNN / context / Poisson + regional monthly loss | 136.30 | 15.05% |

## Reproduce and inspect

```sh
.venv/bin/python -m pip install -r requirements-research.txt
.venv/bin/python scripts/prepare_harmonization_v3.py
.venv/bin/python scripts/train_harmonization_v3.py
.venv/bin/python scripts/audit_harmonization_v3_spatial.py
.venv/bin/python scripts/verify_harmonization_v3.py
.venv/bin/python scripts/report_harmonization_v3.py
.venv/bin/python -m pytest tests -q
```

- Frozen main protocol: `research/harmonization_v3/protocol.json`.
- Supplementary transfer protocol: `research/harmonization_v3/spatial_audit_protocol.json`, specified during development before final selection results.
- Main report and per-day unsampled predictions: `data/research/harmonization_v3/report.json` and `*_predictions.csv.gz`.
- Selection sealed before benchmark/backward predictions: `data/research/harmonization_v3/selection.json`.
- Every neural fit checkpoint: `models/harmonization_v3/*.pt`; final boosted fits: `*.pkl`.
- Per-epoch timings/losses and learned dispersion: `histories.json` / `final_histories.json` in the research data folder.

Production estimator, calendar payload and application are preserved. Full observing exposure is still unknown. A zero report is not proof of no fire or a clear-sky observation. More epochs, finer grids and alternate contexts remain untested; unfavorable results here do not establish that neural methods cannot help.
