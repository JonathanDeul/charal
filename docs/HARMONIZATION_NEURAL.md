# MPS neural harmonization experiments

**Best completed neural candidate: v7 / plr_mlp_conditional.** Statewide 2021–2022 monthly MAE: **475.51**. Target <500: **True**. This is the average of three fixed neural seeds, not a lucky selected seed. Production remains unchanged.

## GPU verification and evaluation policy

The sandbox reports `mps.is_available() == False`, while the authorized outer execution environment reports built=True, available=True. A real MPS matrix forward/backward smoke test succeeded. All rounds below require MPS and raise on unavailability; there is no silent CPU fallback. Inputs, weights and training gradients are placed on MPS. Checkpoints are saved on CPU for portability; independent CPU inference reproduces their saved MPS ensemble predictions within float32 tolerance.

Training uses the same complete paired-month 2013–2020 observations as the deployed seasonal calibration. Development fits 2013–2018; 2019–2020 selects epochs. The resulting epochs are used for fresh 2013–2020 fits. Each config is evaluated on 2021–2022; the config choice is saved before new winner-only benchmark predictions. Each round has three seeds. No 2021+ labels receive training gradients. All historical periods have been repeatedly inspected, so <500 is an exploratory development target, not a pristine independent test or guaranteed future accuracy.

All eligible 224 cells are used in full-month batches, including zeros. The primary score is statewide monthly mean absolute error over the 20 eligible 2021–2022 months, maintaining the original conservative outage policy. No error-based month removal is applied.

## Architectures and objective

- V5: pure neural hurdle-style count mean with fine MODIS descriptors; MLP, full-cell spatial Transformer, and four-day temporal-patch Transformer. No boosted teacher or boosted predictions. Joint local Poisson, binary-presence and direct statewide/north/south monthly losses.
- V6: neural regional totals from weighted pooling or multihead query/key/value attention, with baseline-relative or bounded neural cell allocation. Attention pooling is not mislabeled as the full spatial/temporal Transformer encoder used in v5. Fixed allocation leaves zero-MODIS cells near zero and cannot reconstruct missed detections.
- V7: train-only piecewise-linear numeric embeddings, a per-cell feature-token Transformer or MLP, and positive-target-only conditional-count regression plus presence and aggregate objectives. The feature Transformer attends between input variables rather than between geographic cells or days.

The training-only seasonal ratio is a count offset and extrapolation anchor, not a boosted model. Every candidate learns its presence/count corrections through neural weights and backpropagation. Probabilities are model components and have not been independently calibrated as physical fire probabilities.

## Completed candidates

| Round | Neural config | Selected epoch | 2021–2022 monthly MAE | North monthly MAE | South monthly MAE | Cell-month MAE |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| v5 | mlp_fine_local005 | 20 | 714.60 | 342.69 | 398.74 | 7.51 |
| v5 | mlp_fine_local02 | 40 | 605.84 | 296.45 | 350.86 | 7.47 |
| v5 | spatial_fine_local005 | 80 | 857.74 | 521.27 | 407.22 | 8.39 |
| v5 | spatial_full_local02 | 80 | 690.73 | 340.90 | 373.94 | 8.24 |
| v5 | temporal_fine_local005 | 20 | 736.92 | 334.48 | 432.02 | 7.84 |
| v5 | temporal_fine_local02 | 20 | 688.69 | 259.70 | 442.80 | 7.75 |
| v6 | regional_pool_fixed | 40 | 818.04 | 424.07 | 425.78 | 7.78 |
| v6 | regional_attention_fixed | 40 | 804.81 | 414.06 | 425.23 | 7.78 |
| v6 | regional_attention_flexible | 40 | 838.65 | 438.85 | 440.98 | 7.95 |
| v6 | regional_attention_flexible005 | 40 | 791.56 | 415.77 | 416.07 | 7.85 |
| v7 | raw_conditional | 160 | 687.23 | 371.57 | 339.64 | 7.79 |
| v7 | plr_mlp_conditional | 160 | 475.51 | 251.34 | 294.99 | 8.23 |
| v7 | feature_transformer_conditional | 80 | 785.71 | 401.86 | 414.93 | 7.62 |

## Locked winner audits

| Round winner | 2021–2022 MAE | Known 2023–2025 MAE | Backward 2012 MAE |
| --- | ---: | ---: | ---: |
| v5 / mlp_fine_local02 | 605.84 | 270.33 | 285.29 |
| v6 / regional_attention_flexible005 | 791.56 | 307.67 | 259.06 |
| v7 / plr_mlp_conditional | 475.51 | 271.47 | 148.47 |

Deployed seasonal calibration: selection MAE 730.71, known benchmark 291.33, backward 204.77. V4 boosted candidate: 666.33, 259.74, 165.37. The v4 post-selection fine-feature boosting ablation scored 524.31 on selection only; it was never independently benchmark-confirmed and is not the currently deployed calibration.

## Best neural candidate details

| Period | Statewide MAE | WAPE | North MAE | South MAE | Cell-month MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| selection | 475.51 | 4.68% | 251.34 | 294.99 | 8.23 |
| known_benchmark | 271.47 | 12.31% | 97.68 | 241.62 | 3.78 |
| backward_audit | 148.47 | 4.36% | 110.96 | 136.13 | 4.18 |

| Seed | Selection monthly MAE |
| --- | ---: |
| 42 | 355.96 |
| 43 | 521.97 |
| 44 | 557.36 |

Seed differences show optimizer sensitivity, not independent-data confidence intervals. Greater attention capacity is not assumed to improve calibration: unfavorable full Transformer results are retained.

## Material tradeoffs and unexecuted follow-up

Meeting the <500 statewide target does not satisfy every earlier production safeguard. The best v7 neural ensemble increases selection cell-month MAE from 7.67 to 8.23 (+7.3%). On the known benchmark, northern monthly MAE increases from 92.45 to 97.68 (+5.7%), while statewide and overall cell errors improve. Backward northern 2012 MAE increases from 62.20 to 110.96; statewide backward MAE nevertheless improves. These failures prevent describing this as a uniformly superior spatial reconstruction or silently replacing the deployed model.

Selection signed monthly bias is approximately −418 detections/month, so the lower MAE comes with systematic underprediction. Single-seed selection MAEs range from356 to557; the reported475.51 is the predeclared equal-weight ensemble, not seed selection. Both numerical feature encoding and the changed positive-count objective distinguish v7 from the previous CNNs; the experiment does not establish that extra GPU compute alone caused the improvement.

The initial v7 batch-two implementation was stopped before final selection and benchmark scoring when it was found to differ from the frozen batch-eight protocol. Its artifacts remain under `harmonization_v7_batch2_aborted`, explicitly excluded from the candidate search and result tables. Corrected batch-eight runs produced the results above.

A separate Terra/Aqua feature preparation and modality-fusion architecture were prepared as a possible next round, but v8 was not trained after the v7 ensemble met the requested threshold. A public NASA POWER availability probe also succeeded; no POWER/weather values were used in any reported fit. The new raw-platform descriptors describe detected pixels, not cloud-free exposure.

## Artifacts and sources

Each study has frozen `research/harmonization_vN/protocol.json`, complete `data/research/harmonization_vN/report.json`, sealed `selection.json`, per-epoch histories and per-cell winner predictions. Portable neural checkpoints are under `models/harmonization_vN/`. `data/research/neural_summary/summary.json` contains independent source/protocol, row/metric, checkpoint and target-invariance checks. `candidate_manifest.json` identifies the frozen v7 ensemble and checkpoint hashes. `backend.neural_candidate.NeuralCandidate(root).predict(frame)` provides CPU inference on the derived v4 MODIS feature table (MPS optional); it does not require VIIRS labels. No new uncertainty bands or physical exposure observations were added.

Run `scripts/train_harmonization_v5.py --device mps`, `scripts/train_harmonization_v6.py` or `scripts/train_harmonization_v7.py` in the authorized MPS execution environment; then `scripts/report_neural_harmonization.py`. Checkpoint verifications run on CPU. All scripts use the project `.venv` and `requirements-research.txt`.

Architecture references: [PatchTST](https://arxiv.org/abs/2211.14730), [Earthformer](https://arxiv.org/abs/2207.05833). These experiments are small custom count-regression models, not reproductions or pretrained weights of those systems. [PyTorch MPS documentation](https://docs.pytorch.org/docs/stable/notes/mps.html) distinguishes compiled support from runtime device availability.
