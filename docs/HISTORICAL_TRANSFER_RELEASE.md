# Historical harmonization release — 15 November 2026

**Local active release: `historical-transfer-1`.** The monthly calendar now uses a conservative regional mixture that improves on the original seasonal calibration in all three inspected audit periods. It keeps the original calibration in the north and uses a learned conditional-count model in the south. Before July 2002 it retains the original estimate everywhere because the Terra-only sampling regime lacks matching training support. No public deployment was made.

This release prioritizes backward transfer and regional behavior over the lowest statewide validation error. It is a hybrid of statistical calibration and boosting. The earlier genuine neural MLP remains the lowest-error candidate on the 2021–2022 statewide metric, but does not satisfy the historical/local safeguards. The requested **MAE <500 for 2021–2022 is not met by this released model**.

## Input, target and historical use

One input row is a California **0.5° cell × calendar month**. Inputs are retained MODIS reports: counts, FRP, acquisition/pixel geometry, thermal contrast, within-cell clusters, spatial neighbors, preceding-month MODIS activity, month and coordinates. There are no VIIRS target measurements, calendar-year trend, CAL FIRE perimeter labels or weather measurements among the predictors. The target is the expected number of retained **Suomi-NPP VIIRS detections** in that cell-month, not unique fires or burned area.

The southern expert is the frozen [v4 hurdle-style model](HARMONIZATION_V4.md): a boosted presence probability multiplied by a boosted conditional positive-count mean, with a training-period seasonal count offset. Predictions remain continuous, nonnegative expected counts; no presence threshold is imposed. The northern expert is the original month-specific VIIRS/MODIS ratio. North is defined by cell-center latitude ≥39.5°; south is <39.5°. The fixed boundary can produce a discontinuity in model behavior and is not an ecological border.

Only months through January 2012 use modeled counts in the displayed connected record. From February 2012 onward it uses observed VIIRS, with all original outage masks. January 2012 retains its partial raw reference count while the full-month estimate remains modeled. No undetected hotspot coordinates are reconstructed. Daily map observations, daily seasonal references, event tracking and fire-area tail fitting keep their separate methods.

## Training-period selection

The [frozen release protocol](../research/harmonization_release/protocol.json) compares the original ratio, the rich v4 count model and the v7 numeric-embedding neural ensemble. Mixture weights are chosen from **out-of-fit predictions within 2013–2020**, before computing this mixture's later-period audits:

| Fold | Fit years | Predict years | Direction |
| --- | --- | --- | --- |
| 1 | 2013–2016 | 2017–2018 | Forward |
| 2 | 2013–2018 | 2019–2020 | Forward |
| 3 | 2015–2020 | 2013–2014 | Backward |
| 4 | 2017–2020 | 2015–2016 | Backward |

All folds use the existing independent NASA outage/eligibility policy. Transforms, offsets, neural numeric knots and model weights are fitted within each fold's training years. The neural control uses the frozen v7 architecture, 160 epochs and seeds 42/43/44 on actual MPS. MODIS context contains no reference targets or future-month measurements.

For each region, convex weights 0, .1, .25, .5, .75 and 1 compare baseline and each learned expert. The score weights mean backward-fold monthly MAE by 70% and forward-fold MAE by 30%. A learned blend is admissible only if every fold's regional monthly MAE and cell MAE worsen by at most 5%, and its weighted score improves by at least 5%. Otherwise the region retains the baseline.

This selects **north: baseline, south: 100% v4**. The final experts retain their 2013–2020 fits; audit targets do not refit their weights. `training_selection.json` is saved without audit results before `report.json` is created. The later promotion gate requires ≥5% statewide improvement in each audit period, with no >5% regional or overall-cell degradation. All gates pass.

The choice of model families, safeguards and regions was informed by earlier historical experiments. Although this mixture's weights use only training-period folds, **none of these historical periods is a new independent test**. The 2012 check is one early reference year, not a validation of all pre-2012 conditions. Repeated development, dependent fire activity and historical sensor changes limit the strength of the result.

## Results against the original active calibration

Monthly MAE measures absolute error in statewide detection totals; cell MAE averages absolute error over all evaluated cells and months, including zeros. Lower is better. Eligible months: 20 for 2021–2022, 31 for 2023–2025 and 10 for February–December 2012 (March excluded by the outage policy).

| Inspected period | Original monthly MAE | Release monthly MAE | Reduction | Original cell MAE | Release cell MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2021–2022 | 730.71 | **674.31** | 7.7% | 7.671 | **7.187** |
| Known benchmark 2023–2025 | 291.33 | **256.00** | 12.1% | 3.981 | **3.613** |
| Backward check 2012 | 204.77 | **111.93** | 45.3% | 3.889 | **3.475** |

| Period | Region | Original monthly MAE | Release monthly MAE |
| --- | --- | ---: | ---: |
| 2021–2022 | North | 358.69 | 358.69 |
| 2021–2022 | South | 394.97 | **345.47** |
| 2023–2025 | North | 92.45 | 92.45 |
| 2023–2025 | South | 242.18 | **225.73** |
| 2012 | North | 62.20 | 62.20 |
| 2012 | South | 169.94 | **92.08** |

The improvement does not mean every error measure improves. Statewide mean signed error (prediction minus reference) changes from −85.87 to −208.92 on 2021–2022, from −7.70 to −105.92 on 2023–2025, and from +188.23 to +87.95 in 2012. The release has a greater aggregate underprediction bias on the forward periods despite lower MAE and RMSE. Reported uncertainty and prospective checks remain necessary.

## Neural and Transformer comparison

The earlier [v7 numeric-embedding MLP ensemble](HARMONIZATION_NEURAL.md), trained on MPS, achieves 475.51 / 271.47 / 148.47 statewide MAE in the three periods above. Its 2021–2022 cell error is worse than the baseline, and its northern benchmark and northern backward errors worsen. The new training-only transfer selection therefore does not choose it for either region under the frozen safeguards.

This follow-up also completed three platform-separated neural configurations using 42 additional Terra/Aqua descriptors from the same MODIS archive. Each platform has a training-only seasonal scale; an MLP or a two-layer, 32-dimensional, four-head Transformer learns the fusion. There is no boosted teacher. Epochs are selected on 2019–2020, followed by three-seed 2013–2020 fits. Results are exploratory and remain separate from the release selection:

| Platform model | 2021–2022 MAE |
| --- | ---: |
| MLP, local weight .05 | 696.10 |
| Transformer, local weight .05 | **679.41** |
| Transformer, local weight .01 | 766.98 |

The selected platform Transformer has MAE 265.80 on the known benchmark and 199.07 in 2012. It does not justify replacing the regional release. All histories, choices, seed diagnostics and predictions are retained in `data/research/harmonization_v8/`; its frozen protocol is `research/harmonization_v8/protocol.json`. These are completed experiments, replacing the earlier documentation's “unexecuted follow-up” status.

## Two distinct uncertainty summaries

**Reference-disagreement bands.** After freezing the mixture, residuals are calibrated on the 20 eligible 2021–2022 months. Counts are aggregated to state/north/south **before** calibration. The score is `abs(reference - prediction) / sqrt(prediction + 1)`. At nominal level `c`, the empirical quantile uses rank `ceil((n + 1) * c)`; predictions receive symmetric scaled widths clipped at zero. With n=20, the 95% band uses the maximum calibration residual and is especially coarse.

| Audit | Region | Empirical coverage, nominal 80% | Empirical coverage, nominal 95% |
| --- | --- | ---: | ---: |
| Known 2023–2025 | State | 26/31 = **83.9%** | 31/31 = 100% |
| Known 2023–2025 | North | 26/31 = **83.9%** | 30/31 = 96.8% |
| Known 2023–2025 | South | 21/31 = **67.7%** | 31/31 = 100% |
| Backward 2012 | State | 10/10 = 100% | 10/10 = 100% |
| Backward 2012 | North | 8/10 = 80% | 10/10 = 100% |
| Backward 2012 | South | 10/10 = 100% | 10/10 = 100% |

The southern 80% band undercovers the known benchmark. Calibration-period coverage is 85% at nominal 80% and 100% at nominal 95%, an in-sample diagnostic. Temporal dependence, repeated model development and historical shift prevent a guaranteed coverage interpretation. The state's historical chart uses its **newly calibrated 80% aggregate band**, not the old model's band. Cell bands are explicitly local diagnostics and must never be summed. Custom AOIs receive no calibrated aggregate interval.

**Training-data variability.** There are 39 complete refits with seed 497. Each resamples four consecutive two-year blocks from 2013–2020 with replacement, refits the ratio and southern learner, and keeps the chosen region weights fixed. Predictions are aggregated within each refit before taking the 5th/50th/95th percentiles. These descriptive 90% ranges measure training-year variability. They are saved separately from residual bands and do not quantify all model-selection uncertainty, irreducible error or historical sensor bias. No numeric pre-2012 coverage guarantee is claimed for either summary, especially in the Terra-only regime.

## Integration, reproduction and restoration

The local runtime files `data/processed/analysis.json` and `analysis.json.gz` contain the release's precomputed estimates. The API does not load PyTorch or scikit-learn to serve them. Model metadata, source hashes, original-baseline comparisons, residual diagnostics, separate bootstrap ranges and sampling-regime flags are exported. All 17 missing months, raw sensor counts, observed VIIRS values and unrelated scientific sections are preserved. The rebuilt source-accurate grid has 224 cells; the original published grid omitted one empty boundary cell, so reference totals are unchanged.

`models/harmonization.pkl` remains the original v1 estimator for reproducible comparisons. The new offline inference package is `models/harmonization_release/candidate.pkl`; the active prepared-release manifest is `models/harmonization_release/active_manifest.json`. Load trusted local pickle files only. The promotion script checks protocol/package/uncertainty/source hashes and scientific invariants before writing either runtime file.

With the existing prepared source features and frozen expert checkpoints:

```sh
# Training uses MPS; run in a process with access to the Mac GPU.
.venv/bin/python scripts/train_harmonization_release.py
.venv/bin/python scripts/quantify_historical_transfer.py --bootstrap 39
.venv/bin/python scripts/promote_historical_transfer.py
.venv/bin/python scripts/verify_historical_transfer.py --roundtrip
.venv/bin/python -m pytest tests -q
npm --prefix frontend run typecheck
npm --prefix frontend run generate
```

Training reuses existing OOF CSVs; for a materially changed protocol use a separate research directory and recompute folds. Upstream feature and expert preparation commands remain in the v4/neural reports. Re-running `scripts/analyze.py` creates the original v1 artifact; reapply the release afterwards, before `pack_data.py`. Promotion rejects changed source hashes that need a fresh release experiment.

Exact original scientific JSON and original runtime gzip are preserved under `data/research/harmonization_release/original*.json.gz`. Restore the complete original snapshot with:

```sh
.venv/bin/python scripts/promote_historical_transfer.py --restore
```

This restores the complete saved analysis, including its other scientific sections. Reapply with the promotion command above. Exact restore/reapply and idempotent scientific output are checked by `--roundtrip`; timestamps may change. `data/research/harmonization_release/verification.json` records the reproduced predictions, metrics, interval diagnostics, source invariants and API checks. Full automated and local browser checks are recorded in [VERIFICATION.md](VERIFICATION.md).
