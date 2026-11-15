# Contextual Transformer v9 — implemented, not trained

The model and training entrypoint are ready. Implementation verification uses inference only; no optimizer step, fitting of neural weights, or experimental performance result is claimed. The active historical-transfer calendar is unchanged.

## Architecture and inputs

The default network has 1,234,435 trainable parameters: width128, eight heads, three temporal Transformer layers and three spatial Transformer layers, feed-forward width512 and dropout0.1. This is substantially larger than the earlier width64 MLPs. It is factorized attention, not a single quadratic attention matrix over every point/day/statewide cell.

For each target 0.5-degree cell/month:

- An ordered 5x5 neighborhood preserves each neighbor separately. Absolute location uses continuous latitude/longitude and Fourier features with wavelengths16,8,4,2,1 degrees. Relative latitude/longitude offsets (longitude adjusted for latitude), distance and center flags identify neighbor positions. These approximate angular-distance features are not terrain or geodesic measurements.
- Each neighbor supplies **daily** Terra count, Aqua count, FRP sum and daytime count. A temporal encoder processes the entire target month plus three days before/after it. Padding extends shorter months to37 tokens; invalid tokens are masked. Relative day, cyclic day-of-year, in-target-month and source-valid indicators encode timing and support.
- Spatial attention combines the neighbor summaries with a query containing the target cell's monthly MODIS descriptors and seasonal reference. Monthly descriptors retain the v4 geometry, thermal, cluster, neighbor and lag features. All39 source features are standardized using only the fitting years.
- The seasonal reference has five components per target cell/calendar month: mean and standard deviation of log1p MODIS count, frequency of positive MODIS counts, mean log1p FRP, and log1p number of contributing years. It uses only eligible fitting months. For examples from fitted years, the entire example year is excluded. Holdout years use all fitting years. This is MODIS climatology, not a VIIRS target lookup.
- Presence and conditional positive-count heads produce an expected VIIRS count, anchored to a seasonal ratio fitted on training targets. That ratio is the only target-derived input offset; no observed heldout VIIRS or lagged VIIRS is supplied. Neural corrections, presence and additive count components are trained jointly.

Temporal classification tokens are always valid, including at fully unsupported neighbors; unsupported neighbor summaries are excluded from spatial attention. Missing days are distinct from valid days with zero reports. Source masks describe cached geography and documented outages, not cloud-free exposure or successful overpasses. Daily context comes from the cached western-state union, so border-cell context can contain reports outside California; monthly targets and monthly source descriptors remain state-clipped.

The temporal window is symmetric and retrospective. The model is suitable for retrospective harmonization experiments, **not causal forecasting**. The existing daily cache covers2012–2025. This version cannot be presented as a pre2012 backcast until compatible earlier daily features are prepared and historical transfer checked. No additional weather, terrain, vegetation or external downloads were silently introduced.

## Training and evaluation

Development fits2013–2018 and selects epoch count on2019–2020 statewide monthly MAE. Defaults allow600epochs, validation every5epochs and early stopping after60epochs without improvement. AdamW uses learning rate0.0003, weight decay0.01, gradient norm clipping1 and a cosine schedule with5% floor. The final refit uses2013–2020 for the selected number of epochs and the same learning-rate schedule horizon. Every complete paired month includes all224 cells, including zeros, processed in shuffled cell minibatches.

The objective combines positive-only conditional Poisson deviance weighted by1/sqrt(y+1), presence BCE and log1p count smooth-L1. It does not include a direct statewide-total gradient in this version. Monthly totals are used for checkpoint selection and reporting. Therefore comparisons with earlier models also change the training objective and inputs; they are not isolated architecture ablations.

After duration selection is saved, the final model is evaluated on known2021–2022, known2023–2025 and backward2012 periods, with the same outage eligibility rules. Reports contain statewide, regional and cell metrics a paired refitted seasonal-ratio control and, when its local package is present, the currently active historical-transfer model. These periods have all been inspected previously; none is an independent prospective test. The script never promotes a model into the active calendar.

Checkpoints retain architecture, preprocessing, seasonal tables, ratio, optimizer/scheduler state and fitting years. `development_best.pt` and `final_best.pt` are separate. Last checkpoints and histories are atomically replaced. The CLI deliberately refuses nonempty output directories. It currently **does not resume training**, even though optimizer state is retained; use a new output directory for another run. `backend.harmonization_v9.load_checkpoint` restores preprocessing for offline inference from trusted local checkpoints.

## Commands

The existing `.venv` and prepared v3 daily/v4 monthly features are used; no separate feature preparation command is necessary in this workspace. Fresh environments need `requirements-research.txt` and the upstream v3/v4 preparation scripts.

```sh
# Inference-only input/device check, no training:
.venv/bin/python scripts/train_harmonization_v9.py --check-only --device mps

# Development, epoch selection, final refit and historical audit:
.venv/bin/python scripts/train_harmonization_v9.py --device mps --width 128 --heads 8 --temporal-layers 3 --spatial-layers 3 --radius 2 --halo 3 --batch-size 16 --epochs 600 --patience 60 --seed 42 --output models/harmonization_v9/seed42
```

MPS unavailability raises an error; there is no silent CPU fallback. If memory is insufficient, lower `--batch-size` to8 or4. No measured full-training time is available. For three-seed confirmation repeat with seed43/44 and corresponding empty output directories; do not report the most favorable seed as the ensemble result. Width/depth are configurable, for example width192 with eight heads. Start with the default before increasing memory requirements.

Results and checkpoints are written only to the requested research output directory. `manifest.json` records command settings, source hashes and input hashes; `selection.json` seals epoch choice, and `report.json` plus audit CSVs contain actual results when training completes. The protocol is `research/harmonization_v9/protocol.json`.

## Implementation checks

Four focused tests cover leave-year-out reference leakage, continuous location encoding, masked-token invariance with nonzero output weights, and daily context across a year boundary with outage/geographic masks. Real-data CPU and MPS inference checks pass at the default architecture and report zero optimization steps. Full training, convergence, peak training memory and model quality are unverified until the user runs the command.
