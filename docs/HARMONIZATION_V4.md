# Harmonization v4 — improved exploratory candidate

**Frozen candidate: `hurdle_rich__w1.0`.** A two-stage boosted conditional-mean model improves statewide monthly MAE on both 2021–2022 and the already-known 2023–2025 benchmark. It also improves aggregate north/south errors and overall cell-month MAE in both periods. This is an empirical improvement on inspected historical data, not proof of prospective superiority. Production is preserved.

## Model and inputs

Stage 1 predicts the probability of at least one retained SNPP VIIRS report. Stage 2 predicts the conditional mean count given positive activity, using a Poisson boosted regression on positive-target training rows with a seasonal-ratio offset. The final expected count is probability × conditional mean. This is a hurdle-style mean estimator; it is not a fully fitted zero-truncated count-distribution likelihood. There is no hard presence threshold at inference.

Inputs are MODIS-only: the v2 count/FRP/acquisition/geometry features; occupied 0.05° subcells within each 0.5° cell; 8-connected component counts and largest component; FRP quantiles; brightness-minus-background thermal contrast; mean confidence; within-month maximum daily activity and concentration; spatial neighbor totals at two radii; and previous-month/previous-three-month MODIS activity. Static coordinates and calendar-month cycles are included. VIIRS, year, CAL FIRE, and weather are not input predictors. Historical MODIS context before a split start is allowed because it contains no reference labels; no future month is used.

The 0.05° grid is a descriptor of archived point locations, not additional satellite resolution or reconstructed missing fires. Neighbor counts are clipped to California; boundary support is fixed independently of observed fires. All model transforms and eligibility rules are reproducible. No external weather or vegetation data was necessary to obtain this candidate.

## Search and evaluation

Six model families were tried: small/medium offset boosting with richer features, original-feature offset boosting, a two-stage hurdle model, and simple/rich Poisson linear regressions. Each was compared with five convex weights against the seasonal baseline (30 candidates). Linear regularization was chosen on temporal folds 2013–2016 → 2017–2018 and 2013–2018 → 2019–2020. The final family/weight was selected on 2021–2022, requiring ≥5% lower monthly MAE and no >5% cell/north/south degradation. All choices were saved before the selected candidate benchmark/backward predictions. Original eligibility/outage filtering and fitting years 2013–2020 are identical to the deployed calibration.

These evaluation periods were inspected before this follow-up. The number of candidates and repeated use of selection years make the gain exploratory. A future untouched period is needed for independent confirmation. Earlier temporal-fold results are fully retained, including unfavorable ones.

| Period | Baseline monthly MAE | Candidate monthly MAE | Improvement | Baseline cell MAE | Candidate cell MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| selection | 730.71 | 666.33 | 8.8% | 7.67 | 7.27 |
| known_benchmark | 291.33 | 259.74 | 10.8% | 3.98 | 3.52 |
| backward_audit | 204.77 | 165.37 | 19.2% | 3.89 | 3.53 |

| Period | Region | Baseline monthly MAE | Candidate monthly MAE |
| --- | --- | ---: | ---: |
| selection | north | 358.69 | 347.70 |
| selection | south | 394.97 | 345.47 |
| known_benchmark | north | 92.45 | 60.11 |
| known_benchmark | south | 242.18 | 225.73 |
| backward_audit | north | 62.20 | 108.36 |
| backward_audit | south | 169.94 | 92.08 |

**Material backward-transfer limitation:** Northern California in 2012 worsens from 62.20 to 108.36 monthly MAE, despite a statewide improvement. Pre-2012 application cannot be directly verified with VIIRS. There is no claim that the candidate improves every ecosystem, event or historical regime.

## Null inputs and extremes

| Period | Stratum | Baseline cell-month MAE | Candidate cell-month MAE | Candidate group signed bias |
| --- | --- | ---: | ---: | ---: |
| selection | all_zero_modis | 0.78 | 0.97 | -7.9% |
| selection | viirs_only | 3.18 | 2.21 | -62.5% |
| selection | both_zero | 0.00 | 0.57 | undefined (zero reference total) |
| selection | high_activity | 629.86 | 652.24 | -0.1% |
| known_benchmark | all_zero_modis | 0.95 | 1.10 | -25.6% |
| known_benchmark | viirs_only | 3.61 | 2.63 | -68.4% |
| known_benchmark | both_zero | 0.00 | 0.55 | undefined (zero reference total) |
| known_benchmark | high_activity | 590.55 | 453.23 | +5.2% |
| backward_audit | all_zero_modis | 0.63 | 0.88 | +13.1% |
| backward_audit | viirs_only | 3.08 | 2.07 | -60.3% |
| backward_audit | both_zero | 0.00 | 0.58 | undefined (zero reference total) |
| backward_audit | high_activity | 573.64 | 573.08 | -8.3% |

VIIRS-only cases improve, but predicted activity in truly empty cells makes the combined zero-MODIS stratum worse. High-activity absolute error is slightly worse on selection (27 cases) and better on the benchmark (only four cases); aggregate bias is closer to zero than the baseline in both periods. The missing-small-fire problem is not solved.

## Confirmation and feature ablations

Geographic transfer: refit only on centers >2° from northern audit cells, so 1° source-neighbor radii do not overlap. Candidate northern monthly MAE 123.53 versus paired baseline 121.94; +1.3%, within the fixed 5% tolerance. This diagnostic does not establish global geographic transfer.

CAL FIRE sensitivity drops an entire training cell-month if any daily input support is associated with a known cross-boundary linked event. It removes 1,113 training cell-months. Paired refit results:

| Period | Guarded baseline MAE | Guarded candidate MAE |
| --- | ---: | ---: |
| selection | 835.71 | 718.14 |
| known_benchmark | 316.94 | 286.08 |

Both guarded comparisons also pass the original statewide/cell/regional criteria. CAL FIRE remains a split-protection/evaluation source; incomplete links and dates prevent a guarantee of event independence.

The following feature ablations were computed **after selection**, on 2021–2022 only, with fixed two-stage hyperparameters. They did not replace the frozen candidate or trigger another benchmark search.

| Two-stage feature set | Selection monthly MAE |
| --- | ---: |
| original_only | 606.30 |
| original_plus_fine | 524.31 |
| original_plus_context | 796.43 |
| full | 666.33 |

Fine structure is promising; more neighboring/history features are not uniformly beneficial. The full selected model is not claimed to be the best possible feature subset.

The full candidate's mean temporal development-fold MAE is 1039.11, versus approximately 932.67 for the seasonal control in v2. Those shorter-training-fold results are unfavorable. Later-period improvements and the event-guard sensitivity therefore support a candidate for further prospective testing, not a universal model-superiority claim.

## Artifacts and reproduce

```sh
.venv/bin/python scripts/prepare_harmonization_v4.py
.venv/bin/python scripts/train_harmonization_v4.py
.venv/bin/python scripts/audit_harmonization_v4.py
.venv/bin/python scripts/report_harmonization_v4.py
.venv/bin/python -m pytest tests -q
```

- Frozen candidate package: `models/harmonization_v4/candidate.pkl` (trusted local pickle only).
- Complete development and all 30 selection results: `data/research/harmonization_v4/report.json`.
- Selection checkpoint sealed before new audits: `selection.json`.
- Geographic, CAL FIRE and post-selection feature checks: `audit.json`.
- Full-period research predictions and outage-masked historical comparison: `all_period_cell_predictions.csv.gz`, `historical_comparison.csv`.
- Independent ratio parity, source/protocol hashes, saved predictions, reference/year input leakage and count-support verification: `verification.json`.
- Production estimator and prepared calendar remain unchanged. New uncertainty bands have not been calibrated; existing baseline bands must not be reused for the candidate.
