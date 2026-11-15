# Input-conditioned error analysis — 15 November 2026

Exploratory analysis of saved predictions; no retraining or change to the frozen model-selection rule. Primary candidate: pooled West Negative-Binomial GAM (`nb_gam_west`). Control: current seasonal-ratio calibration. All units below are California **cell-months**, not individual fires. Outage-flagged paired months are excluded.

## selection_2021_2022

4,480 cell-months; 203,026 VIIRS reports.

| Presence class | Cell-months | Fraction of cells | VIIRS reports | Fraction of VIIRS | Ratio MAE/cell | West NB MAE/cell | West NB predicted total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MODIS=0, VIIRS=0 | 2,493 | 55.6% | 0 | 0.0% | 0.00 | 0.42 | 1,047.7 |
| MODIS=0, VIIRS>0 | 817 | 18.2% | 2,598 | 1.3% | 3.18 | 2.74 | 361.8 |
| MODIS>0, VIIRS=0 | 81 | 1.8% | 0 | 0.0% | 5.82 | 4.87 | 394.2 |
| MODIS>0, VIIRS>0 | 1,089 | 24.3% | 200,428 | 98.7% | 28.74 | 32.29 | 192,541.4 |

| MODIS reports per cell-month | Cell-months | VIIRS reports | Ratio MAE/cell | West NB MAE/cell | Ratio signed error | West NB signed error | Fraction of West NB absolute cell error |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 3,310 | 2,598 | 0.78 | 0.99 | -2,598 | -1,188 | 8.5% |
| 1–4 | 710 | 5,341 | 5.10 | 4.80 | -437 | -858 | 8.8% |
| 5–19 | 329 | 8,644 | 12.75 | 11.17 | 1,768 | 115 | 9.5% |
| 20–99 | 82 | 10,282 | 38.57 | 29.36 | 1,084 | -253 | 6.2% |
| 100–499 | 22 | 20,465 | 172.18 | 153.41 | 2,624 | 834 | 8.7% |
| 500+ | 27 | 155,696 | 629.86 | 840.32 | -4,159 | -7,330 | 58.4% |

### region

| Group | Cell-months | Ratio MAE/cell | West NB MAE/cell | Ratio monthly-total MAE | West NB monthly-total MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| North | 1,100 | 15.85 | 19.71 | 358.69 | 443.30 |
| South | 3,380 | 5.01 | 5.08 | 394.97 | 477.10 |

### season

| Group | Cell-months | Ratio MAE/cell | West NB MAE/cell | Ratio monthly-total MAE | West NB monthly-total MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| DJF | 1,344 | 2.70 | 2.61 | 128.50 | 189.85 |
| JJA | 896 | 16.66 | 20.92 | 1526.77 | 357.59 |
| MAM | 1,120 | 2.64 | 2.53 | 192.86 | 217.57 |
| SON | 1,120 | 11.48 | 12.28 | 1354.38 | 1960.77 |

### Other input associations (positive MODIS cells only)

| Feature | Group | Cell-months | Ratio MAE/cell | West NB MAE/cell |
| --- | --- | ---: | ---: | ---: |
| terra_bin | Aqua only | 296 | 4.70 | 4.46 |
| terra_bin | Terra up to 25% | 63 | 11.02 | 9.63 |
| terra_bin | Mixed 25–75% | 485 | 56.42 | 65.34 |
| terra_bin | Terra 75–100% | 47 | 18.01 | 13.50 |
| terra_bin | Terra only | 279 | 5.28 | 4.67 |
| day_bin | Night only | 49 | 7.14 | 6.64 |
| day_bin | Day up to 25% | 9 | 16.92 | 18.63 |
| day_bin | Mixed 25–75% | 140 | 164.15 | 201.36 |
| day_bin | Day 75–100% | 47 | 24.35 | 18.92 |
| day_bin | Day only | 925 | 7.72 | 6.47 |
| frp_mean_bin | (-inf, 11.817] | 335 | 5.16 | 4.74 |
| frp_mean_bin | (11.817, 20.6] | 279 | 9.37 | 7.23 |
| frp_mean_bin | (20.6, 41.033] | 284 | 11.45 | 10.29 |
| frp_mean_bin | (41.033, inf] | 272 | 88.88 | 106.71 |
| footprint_mean_bin | (-inf, 1.171] | 295 | 5.39 | 4.88 |
| footprint_mean_bin | (1.171, 1.565] | 293 | 9.70 | 8.52 |
| footprint_mean_bin | (1.565, 2.21] | 303 | 41.99 | 44.43 |
| footprint_mean_bin | (2.21, inf] | 279 | 52.38 | 65.07 |
| detection_days_bin | (-inf, 1.0] | 526 | 5.31 | 4.87 |
| detection_days_bin | (1.0, 2.0] | 224 | 8.09 | 7.35 |
| detection_days_bin | (2.0, 3.0] | 125 | 13.94 | 11.70 |
| detection_days_bin | (3.0, inf] | 295 | 86.18 | 101.30 |

## known_benchmark_2023_2025

6,944 cell-months; 68,384 VIIRS reports.

| Presence class | Cell-months | Fraction of cells | VIIRS reports | Fraction of VIIRS | Ratio MAE/cell | West NB MAE/cell | West NB predicted total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MODIS=0, VIIRS=0 | 3,872 | 55.8% | 0 | 0.0% | 0.00 | 0.42 | 1,627.9 |
| MODIS=0, VIIRS>0 | 1,384 | 19.9% | 5,003 | 7.3% | 3.61 | 3.17 | 613.1 |
| MODIS>0, VIIRS=0 | 143 | 2.1% | 0 | 0.0% | 5.42 | 4.94 | 706.0 |
| MODIS>0, VIIRS>0 | 1,545 | 22.2% | 63,381 | 92.7% | 14.15 | 12.93 | 59,437.3 |

| MODIS reports per cell-month | Cell-months | VIIRS reports | Ratio MAE/cell | West NB MAE/cell | Ratio signed error | West NB signed error | Fraction of West NB absolute cell error |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 5,256 | 5,003 | 0.95 | 1.14 | -5,003 | -2,762 | 22.5% |
| 1–4 | 1,131 | 7,677 | 4.93 | 4.64 | 173 | -268 | 19.7% |
| 5–19 | 434 | 11,492 | 14.00 | 11.00 | 2,633 | 151 | 17.9% |
| 20–99 | 98 | 12,874 | 51.18 | 46.21 | 1,985 | 204 | 17.0% |
| 100–499 | 21 | 19,046 | 171.96 | 198.22 | -1,195 | -2,785 | 15.6% |
| 500+ | 4 | 12,292 | 590.55 | 490.77 | 1,168 | -540 | 7.4% |

### region

| Group | Cell-months | Ratio MAE/cell | West NB MAE/cell | Ratio monthly-total MAE | West NB monthly-total MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| North | 1,705 | 4.66 | 4.93 | 92.45 | 125.54 |
| South | 5,239 | 3.76 | 3.49 | 242.18 | 243.15 |

### season

| Group | Cell-months | Ratio MAE/cell | West NB MAE/cell | Ratio monthly-total MAE | West NB monthly-total MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| DJF | 2,016 | 2.72 | 2.69 | 282.98 | 250.37 |
| JJA | 1,568 | 5.91 | 5.31 | 477.31 | 347.08 |
| MAM | 1,792 | 2.24 | 2.25 | 103.16 | 144.82 |
| SON | 1,568 | 5.65 | 5.70 | 331.15 | 593.09 |

### Other input associations (positive MODIS cells only)

| Feature | Group | Cell-months | Ratio MAE/cell | West NB MAE/cell |
| --- | --- | ---: | ---: | ---: |
| terra_bin | Aqua only | 518 | 5.46 | 5.34 |
| terra_bin | Terra up to 25% | 97 | 13.93 | 14.03 |
| terra_bin | Mixed 25–75% | 559 | 27.54 | 25.18 |
| terra_bin | Terra 75–100% | 55 | 14.68 | 9.27 |
| terra_bin | Terra only | 459 | 4.93 | 4.29 |
| day_bin | Night only | 80 | 6.10 | 6.49 |
| day_bin | Day up to 25% | 7 | 7.53 | 8.83 |
| day_bin | Mixed 25–75% | 166 | 60.30 | 60.17 |
| day_bin | Day 75–100% | 61 | 26.23 | 24.47 |
| day_bin | Day only | 1,374 | 7.63 | 6.27 |
| frp_mean_bin | (-inf, 11.817] | 508 | 4.98 | 4.68 |
| frp_mean_bin | (11.817, 20.6] | 424 | 7.59 | 6.23 |
| frp_mean_bin | (20.6, 41.033] | 420 | 15.18 | 14.23 |
| frp_mean_bin | (41.033, inf] | 336 | 31.31 | 28.83 |
| footprint_mean_bin | (-inf, 1.171] | 433 | 5.26 | 4.82 |
| footprint_mean_bin | (1.171, 1.565] | 454 | 7.32 | 6.53 |
| footprint_mean_bin | (1.565, 2.21] | 420 | 19.25 | 19.55 |
| footprint_mean_bin | (2.21, inf] | 381 | 23.51 | 19.48 |
| detection_days_bin | (-inf, 1.0] | 826 | 4.83 | 4.57 |
| detection_days_bin | (1.0, 2.0] | 321 | 7.66 | 6.57 |
| detection_days_bin | (2.0, 3.0] | 200 | 11.90 | 10.03 |
| detection_days_bin | (3.0, inf] | 341 | 40.52 | 37.52 |

## Interpretation

For zero MODIS counts, the ratio prediction is exactly zero. In the GAM the entire multiplicative term is also zero, so only `softplus(region_floor)` remains: within the same ecological region, **all zero-MODIS inputs get the same prediction**, regardless of month or state. This follows from the fitted architecture, not a thresholded fire/no-fire classifier. It cannot identify which of the many zero-MODIS cell-months contain VIIRS reports. Positive fractional expected counts are not literal recovered detections.

The all-zero group can dominate row counts while high-activity groups dominate absolute error. Always compare cell frequency, VIIRS mass, and error contribution separately. A large percentage error in a near-zero group does not establish the cause of statewide monthly error. The JSON includes exact monthly signed-error decompositions and all six model variants, ecological-region and month tables, joint region/count strata and largest errors.

These are post-hoc associations, not causal effects of FRP, platform or geometry. Higher-count fires naturally have larger absolute errors; marginal feature strata can reflect that. No outage or extreme month was removed on the basis of model error. See `data/research/harmonization_v2/diagnostics.json` for complete results, bin thresholds and input hashes.
