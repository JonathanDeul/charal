# Charal — California Fire Observatory

A real-data, regional proof of concept for [NASA Space Apps 2026: Harmonization of MODIS and VIIRS Hot Spots](https://www.spaceappschallenge.org/2026/challenges/modis-and-viirs-hot-spots/?tab=details).

English Nuxt + Tailwind frontend, FastAPI backend, offline reproducible scientific analysis. California, 2001–2025. No login, database, external tile service, or runtime API key is required. Deployment is **prepared, not published**, as requested.

## Run locally

Requirements: Python 3.11+, Node **24.15+** (or a compatible recent Node 22/26), npm. The existing local `.venv` and frontend dependencies are already installed.

```bash
./scripts/dev.sh
```

Open **http://127.0.0.1:3000**. FastAPI documentation: http://127.0.0.1:8000/docs. Stop both processes with Ctrl-C.

Fresh installation:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm --prefix frontend ci
./scripts/dev.sh
```

The compact prepared dataset is included under `data/processed/`: `observations.npz`, `events.json.gz`, `analysis.json.gz`, `california.geojson`, and `map-context.geojson`. These suffice to run the app. The full local NASA CSV and cached US archives are intentionally excluded from deployment.

## Active monthly harmonization

The local calendar now uses **historical-transfer-1**: the original seasonal calibration in northern cells, and a learned conditional-count model in southern cells, selected using forward/backward folds within 2013–2020. Statewide monthly MAE improves from **730.71 to 674.31** on 2021–2022, **291.33 to 256.00** on the known 2023–2025 benchmark, and **204.77 to 111.93** in the 2012 backward check. Northern estimates remain unchanged. All historical audit periods have been inspected; these are exploratory transfer results, not prospective confirmation.

New empirical residual bands and 39 block-bootstrap refits quantify separate aspects of uncertainty. Pre-July-2002 Terra-only estimates retain the original calibration; raw observations, observed VIIRS and outage masks remain unchanged. The neural MLP still achieves the best 2021–2022 statewide score (475.51), but its local/northern transfer failures prevent a blanket historical replacement. The regional release does not meet that <500 target. See [release results, uncertainty and restoration](docs/HISTORICAL_TRANSFER_RELEASE.md). Daily/event outlier methods remain separate.

## What works

- NASA hotspot map with both sensors or individual sensor layers. Prepared Census geography and city labels work without map API keys.
- **Seasonal outliers:** inferred observed events with separate occurrence/activity scores, local 10 km references and seasonal windows across years. First recorded activity remains an outlier even with limited support; regional references affect only activity strength. Event points, reason filters, CAL FIRE overlap labels, JSON export and the original cell baseline are available. See [v2 method and audit](docs/EVENT_OUTLIERS_V2.md).
- Daily map animation with Play/Pause, a keyboard-accessible date slider, adjustable speed, and one-day or trailing three-day windows. Choose dates across months or years; older pixels/points fade, and the 1 km grid recomputes statistics for the displayed window. Under **Time**, select **Daily animation · UTC**.
- Monthly burning calendar for 2001–2025; click any month to update the map and historical comparison.
- Preset regions, two-corner map selection, and keyboard-accessible coordinate entry.
- Observed MODIS/VIIRS counts and a VIIRS-reference historical activity series. Known incomplete sensor-months stay explicitly unavailable.
- Regional transfer calibration, original controls, known historical audits, geographic checks and explicit uncertainty diagnostics.
- Fire-area tail fitting, threshold estimation, bootstrap compatibility tests, empirical parameter intervals, lognormal/exponential comparisons, and complex-record sensitivity.
- Monthly CSV, selected perimeter-record CSV, sampled map-detection CSV, scientific chart SVG, analysis/provenance JSON.
- Source and method explanations in the app. Responsive desktop/mobile layouts.

## What the actual research found

The prepared archive contains **1,315,630** state-clipped NASA detections. A documented vegetation/confidence rule retains **1,169,069** (297,730 MODIS; 871,339 Suomi NPP VIIRS). The CAL FIRE source provides **8,699 perimeter records**, not a guaranteed set of independent fires.

In the original v1 study, model families and the time split were fixed before final reporting. Independently sourced NASA outage flags exclude incomplete paired months. Training: 2013–2020; validation: 2021–2022; original test: 2023–2025. The clean original test had 31 months; subsequent studies treat those years as a known benchmark.

| Method | Test monthly MAE | Test WAPE |
| --- | ---: | ---: |
| Monthly-ratio calibration | 291.33 | 13.21% |
| Trained boosted-tree ML | 513.29 | 23.27% |
| Seasonal mean | 3516.66 | 159.42% |

Original v1 validation selected the ratio baseline. That estimator is preserved at `models/harmonization.pkl`, and its original ML control at `models/boosted_candidate.pkl`. The later active release described above supersedes the original calendar calibration.

A separate [harmonization v2 experiment](docs/HARMONIZATION_V2.md), completed on 15 November, reprocessed 2.37 million detections across five western states and trained baseline-anchored Negative-Binomial/Poisson GAMs and a boosted correction. The pooled West model reduced statewide validation MAE by 7.9% but worsened regional and cell errors, failing its predeclared promotion gate. At the end of v2 the calendar retained the original calibration. Real MODIS/VIIRS observation masks were acquired as a bounded pilot; they are not yet full-period model inputs. The already-inspected 2023–2025 scores are explicitly labeled a known benchmark in this follow-up.

The [daily context experiment (v3)](docs/HARMONIZATION_V3.md) compares point and 7-day/5×5-patch inputs for boosting and small neural networks, with three neural seeds and CAL FIRE event-boundary guards. Context lowers boosting monthly MAE by 14.0% on 2021–2022 and 8.7% on the known 2023–2025 benchmark. The first CNN configurations do not consistently improve statewide performance; they show some benefit in a buffered geographic-transfer diagnostic. V3's purged training population differs substantially from v1, so within-v3 controls and the unchanged deployed reference are reported separately. At that stage production remained unchanged.

[Harmonization v4](docs/HARMONIZATION_V4.md) found an improved **exploratory candidate**: a two-stage boosted count mean with finer MODIS descriptors. Using the original baseline's eligible 2013–2020 observations, its statewide monthly MAE improves from 730.71 to 666.33 on 2021–2022 and from 291.33 to 259.74 on the known 2023–2025 benchmark; north/south and overall cell errors improve in both periods. Paired CAL FIRE-purged sensitivity fits confirm the forward improvement. Important failures remain: Northern California in 2012, combined zero-MODIS cell errors, and shorter-training development folds. Multiple comparisons and previously inspected periods require prospective confirmation. The trained candidate and research backcasts were saved separately; v4 alone did not replace v1. The later regional release above adds new uncertainty calibration.

The [MPS neural experiments](docs/HARMONIZATION_NEURAL.md) tested 13 neural configurations, including spatial, temporal-patch and feature-token Transformers. A three-seed MLP ensemble with piecewise-linear numeric embeddings reaches **475.51 monthly MAE on 2021–2022**, below the requested500, and271.47 on the known2023–2025 benchmark. It is a genuine neural count model with a training-only seasonal count offset and no boosted teacher. Local tradeoffs remain: selection cell errors increase7.3%, known-benchmark northern error increases5.7%, and northern2012 backcasts worsen. The neural candidate was not promoted into the calendar. Portable inference is available through `backend.neural_candidate.NeuralCandidate(root).predict(derived_modis_frame)`; the frozen checkpoint manifest is under `data/research/neural_summary/`.

The full-period perimeter sample has 1,966 records above the 300-acre floor. Its fitted tail starts at about 130.6 ha (1,918 records), with density exponent α≈1.544. A semiparametric compatibility bootstrap gives **p=0.005 (199 replicates)**, rejecting a simple power-law description at this selected threshold. The conditional lognormal has higher likelihood; removing linked/named complex records preserves the qualitative conclusion. A power law is a tested hypothesis, not a promised finding.

## Scientific limits that matter

- A hotspot is a thermal detection, not a unique fire or burned-area measurement.
- Confidence fields have different meanings across sensors. Filtering them does not make them calibrated probabilities.
- The archive mixes MODIS version strings; it is not a uniform reprocessed collection. Orbit drift, exposure, sensitivity and algorithm changes can remain after calibration. Aqua starts in July 2002; earlier estimates extrapolate across a Terra-only sampling regime.
- Seventeen known-incomplete calendar months are masked. No listed NASA outage does **not** establish complete, cloud-free observations. January 2012 uses a modeled estimate because the reference starts partway through that month.
- Custom calendar AOIs select **0.5° grid-cell centers**; point-map filtering uses exact point coordinates. Their boundary counts can differ. Perimeter AOIs select centroids and keep whole reported area.
- Perimeter areas may overlap and include unburned islands. Their sum is not unique burned area. Reporting thresholds and historical omissions limit tail inference.
- Bootstrap p-values and intervals have finite-sample and independence assumptions; see the complex sensitivity and full methods. Interactive subset fits omit the expensive compatibility bootstrap and clearly say so.
- Drossel–Schwabl is documented as a future explanatory experiment. No simulation or fire-spread forecast is claimed.

## Reproduce the snapshot and analysis

These commands use public official endpoints. Existing `.env` keys are not needed for this historical snapshot and never enter the browser bundle.

```bash
.venv/bin/python scripts/fetch_data.py
.venv/bin/python scripts/fetch_coverage.py
.venv/bin/python scripts/analyze.py --bootstrap 199 --grid 0.5
.venv/bin/python scripts/promote_historical_transfer.py
.venv/bin/python scripts/pack_data.py
```

The downloader caches approximately 800 MB of US archives before clipping California. The promotion step requires the locally trained release package and matching source hashes; a fresh checkout must first reproduce the research features/experts using the [release instructions](docs/HISTORICAL_TRANSFER_RELEASE.md). `analyze.py` alone rebuilds v1. Review `scripts/fetch_data.py --help` for available options. Geography for the prepared basemap is already included; exact source queries are in [docs/MAP_DATA.md](docs/MAP_DATA.md).

## Verification

```bash
.venv/bin/python -m pytest tests -q
npm --prefix frontend run typecheck
npm --prefix frontend run generate
```

See [docs/VERIFICATION.md](docs/VERIFICATION.md) for the actual browser checks and limits. Source provenance: [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md). Scientific definitions: [docs/METHODS.md](docs/METHODS.md).

## Deploy later

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). No deployment was made. Root `vercel.json` builds the static Nuxt application and routes `/api/*` to FastAPI. Raw archives, environment files, training weights, and development dependencies are excluded from the deployment upload.

## Submission preparation

[docs/SUBMISSION.md](docs/SUBMISSION.md) contains English project text, source credits, an AI-use disclosure draft, a short demo script, and a seven-slide pitch outline. Review it against the current Cambridge event instructions and the required fields on your team page before submitting. The general 2026 website deadline is Sunday, November 15 at 11:59 PM local time; a Cambridge-specific earlier presentation/submission timetable has not been verified.

## Attribution

NASA FIRMS / LANCE / Earthdata; CAL FIRE FRAP and cooperating agencies; US Census Bureau. Research references and exact URLs are included in the method/source documents. No NASA endorsement is implied.

