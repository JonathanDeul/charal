# Verification — 14 November 2026

**15 November active monthly release:** [historical-transfer-1](HISTORICAL_TRANSFER_RELEASE.md) passes all statewide/regional/cell promotion criteria in the known forward and 2012 backward audits. The training-only regional choice, saved predictions, all metrics, residual coverage and 39 block-bootstrap aggregate quantiles are independently reproduced. The 300-month/224-cell runtime preserves raw/reference values, all 17 missing months, unrelated scientific fields and original pre-Aqua estimates. Exact original JSON/gzip rollback and reapplication are verified; the active manifest follows restoration. Real-data API checks verify the release, source totals, custom-AOI interval suppression and CSV baseline fields. All **100 tests pass**, including interval endpoint roundoff, count mixing and release export regressions. Nuxt typecheck and static generation pass. The in-app browser at localhost:3000 visibly displays the active label, prediction curves, MAE 256 versus 291.3, and the empirical-band caveat. No public deployment was performed. See `data/research/harmonization_release/verification.json` for artifact hashes and checks. The three previously unexecuted platform neural fits have now completed on MPS and remain research candidates.

**15 November neural/MPS follow-up:** [13 neural configurations](HARMONIZATION_NEURAL.md) completed three-seed development/final fits on actual MPS. The corrected frozen v7 numeric-embedding ensemble achieves475.51 on2021–2022 and271.47 on the known2023–2025 benchmark. All93 current tests pass. Independent checks verify source/protocol hashes, sealed pre-benchmark selection, all reference rows/metrics, target-input invariance and CPU reproduction of MPS checkpoints. The portable inference loader reproduces all4480 selection cell-month predictions. Reports retain the adverse cell/northern/backward results. The aborted batch-two development attempt is preserved and excluded; the platform-fusion follow-up was unexecuted at that stage and has since completed, as recorded above. The v7 neural model itself was not promoted.

**15 November v4 candidate:** [harmonization v4](HARMONIZATION_V4.md) evaluated six model families and 30 baseline blends, sealing selection before new candidate benchmark/backward predictions. All 62 current tests pass. Independent checks reproduce the actual deployed baseline's monthly ratio parameters, saved candidate predictions and metrics, source/protocol hashes, reference/year input invariance and positive conditional-count support. Forward selection/benchmark gates, paired event-purged refit gates and the 5% geographic-transfer tolerance pass; backward northern and combined zero-input failures are retained in the report. The 300-month research comparison preserves all 17 outage masks and observed VIIRS values. Production files remain unchanged; hashes are recorded in `data/research/harmonization_v4/verification.json`.

**15 November daily-context follow-up:** [harmonization v3](HARMONIZATION_V3.md) completed seven main model/control families, three neural seeds, development epoch selection, later-period/backward evaluation and spatially buffered refits. All 45 current tests pass. Independent artifact checks reproduce monthly reference counts, all reported metrics and checkpoint predictions; verify frozen protocol/source hashes, sealed pre-benchmark selection, and more than 2° spatial center separation between training and northern audit patches. Detailed checks are saved in `data/research/harmonization_v3/verification.json`. Production data and estimator remain unchanged.

**15 November research follow-up:** the separate [harmonization v2 experiment](HARMONIZATION_V2.md) completed six model/control fits plus development and geographic refits. All 30 current tests pass, including count-support, target-leakage, unseen-region, outage-split and unavailable-region regressions. California monthly counts match v1. Real MODIS daily masks (16 files) and one geolocated VIIRS 375m swath were processed; mask pixel classes were checked against their totals. The v2 promotion gate rejects the candidate, so the original application payload and estimator are preserved. No new UI or cloud deployment is claimed.

Scope: local California PoC; deployment preparation only. No public deployment or official challenge submission was performed.

## Automated checks

- **23 tests pass:** 12 scientific tests and 11 API tests. They cover tail fitting/degenerate samples, bootstrap semantics, clean time splits, reference availability, outage masking, shared eligibility rules, monthly aggregation, region/date validation, point filtering, exports, and CSV formula escaping.
- **Nuxt TypeScript check passes.**
- **Nuxt production static generation passes** with Nuxt 4.6.4, Vue 3.5.45 and a compatible Node 26 runtime. Root deployment requests Node 24; use a current compatible minor (24.15+).
- Real prepared-data smoke checks pass: 1,169,069 retained observations; 300 monthly rows; 17 masked months; September 2020 reference count 125,290; selected-month map total 151,453 with 10,000 explicitly sampled displayed points; correct missing pre-VIIRS points; full-state bootstrap and subset no-bootstrap semantics; CSV gap-count columns and nulls; JSON and perimeter CSV exports.
- All 39 NASA annual files passed manifest-byte checks. California state clipping, required fields, times and nonnegative FRP were validated. The independently queried CAL FIRE source count agrees with 8,699 acquired records.
- Geography includes 63 local Census features: 5 states and 58 California counties. No external tiles or map API key are used.

Two non-failing development warnings can occur: the current Starlette TestClient warns about an upcoming HTTP client migration; joblib may fall back to logical core counts in this sandbox.

## Browser checks actually performed

In the in-app browser:

- Full prepared dataset loads through the real FastAPI backend and Nuxt development proxy.
- Desktop two-column layout at 1440×1000 and mobile layout at 390×844 were inspected.
- At 390px, document content width equals viewport width; wide calendar/plot contents scroll inside their own panels.
- Preset region and start/end year selection update map, summary and calendar. Northern California 2020–2021 displays 53,073 MODIS reports, 241,641 VIIRS reports and 237 perimeter records.
- Selecting August 2021 in that regional calendar updates the focused month and map.
- Two-corner map drawing changes the study-area selection to Custom area.
- July 2024 shows an unavailable harmonized value and a known-outage notice (10 listed dates), while raw partial observations remain inspectable.
- The ML pane displays actual clean held-out scores, baseline selection and prediction curves.
- The extreme-fire pane displays 1,966 records above the floor, α≈1.54, empirical bootstrap interval, p=.005 and alternative distributions.
- Mobile navigation opens and selects the extreme-fire page. Hidden navigation is removed from the accessibility tree when closed.
- Export choices are present; a browser SVG-download event was observed. API CSV/JSON payloads were independently inspected. The final SVG export code also adds chart title, selection, legend and source context; its final downloadable bytes were not separately rendered as an artifact.
- Temporary browser viewport overrides and QA servers were cleaned up after verification.

Screenshots: [observatory.jpg](screenshots/observatory.jpg), [extremes.jpg](screenshots/extremes.jpg).

## Limits

- No cloud build/runtime check: Vercel login was invalid and the user requested deployment preparation only. `vercel.json`, `.vercelignore` and runtime entrypoint are prepared; first deployment still requires a preview smoke check.
- No operational forecast or cellular fire simulation is implemented.
- No physical phone, screen reader or cross-browser test was performed. This is a responsive PoC, not a completed accessibility certification.
- Source completeness, processing-version drift, early Terra-only sampling, sensor exposure and perimeter-record independence remain scientific limitations; see METHODS.md and DATA_SOURCES.md.
- npm's compatible security updates removed the original high-severity advisory. Remaining low/moderate notices are in Nuxt/build tooling; this is a statically generated frontend. No forced downgrade was applied.

The full environment is recorded in ENVIRONMENT.txt and frontend/package-lock.json.

## NASA footprint explorer (2026-11-15)

- Repacked 1,169,069 eligible detections with original scan/track dimensions,
  UTC acquisition times and satellite identifiers. No new source observations.
- `/api/fire-map` is unsampled. September 2020 returns 125,290 VIIRS
  observations (10,060 occupied display-grid cells), 26,163 MODIS observations,
  or 151,453 combined. All have valid pixel dimensions in that month.
- API regression covers distinct UTC dates rather than detection counts or
  first/last date span, sensor filtering, max FRP, missing FRP, UTC time formatting,
  day/month boundaries, empty results, invalid dates and outdated packed data.
- Browser checked NASA pixel footprints, detection-day cells, combined legend,
  point overlay, day filter and combined-sensor view. The narrow layout wraps
  controls and keeps the legend inside the map. Canvas simplification is disabled
  so subpixel rectangles remain visible at statewide zoom.
- These are approximate observation footprints and uncalibrated display-grid
  statistics. No burned-area estimate or continuous fire duration was validated.

## Daily map animation (2026-11-15)

- Added a map-local daily timeline with inclusive UTC date ranges across months
  and years, a slider, previous/next day, Play/Pause, three speeds, and one-day
  or trailing three-day windows clipped to the selected start. Calendar and
  harmonization values retain their monthly definitions.
- Pixel/point opacity fades by acquisition-day age in the three-day window.
  The existing 1 km grid aggregates only observations in the displayed window;
  its color bins and detection-day opacity scale remain fixed during playback.
- Playback waits for a response and rendering before advancing to an unbuffered frame,
  stops at the end or on errors, and cancels superseded requests. Editing dates,
  changing sensor/region/month, scrubbing or leaving the map stops playback.
- API accepts paired inclusive `start_date`/`end_date` parameters (2001–2025,
  at most 93 days per request); the animation requests at most three days.
  Existing month/day callers are preserved.
- All 22 API tests pass, including a year-boundary window, sensor/bbox filtering,
  empty dates, window-local FRP/detection-day aggregation and invalid ranges.
  Frontend typecheck and static production generation pass.
- Browser checked daily playback/pause, restart from the end, slider keyboard
  navigation, invalid ranges, pixel and grid views, and 390 px responsive layout.
  The real-data 2020-09-30 through 2020-10-02 VIIRS window returned 6,625
  observations with acquisition dates confined to those three dates.
- No new source data, calibration, fire-front reconstruction or deployment.

### Animation continuity fix (2026-11-15)

The map now retains its visible observations throughout a request. It constructs
the complete replacement layer before swapping layers in the same canvas redraw,
preloads one subsequent day, and keeps up to eight response frames in an LRU
cache. Identical pending requests are shared; superseded active requests and
requests for a replaced region/sensor are cancelled. Date labels and fading
use the committed visible frame, including while a later frame buffers. Truly
empty observation windows still render empty when committed.

Browser playback was checked at Fast speed with the trailing three-day window
and activity grid. The previous immediate clearing is removed; a slow response
holds the previous frame instead of inserting an empty map. Exact frame-rate
or simulated network-throttling measurements were not performed.

## Seasonal activity outliers (2026-11-15)

- Added real daily support on the fixed 224-cell California grid and a separate
  smooth seasonal MODIS calibration. The 0.5° cell rank uses equal-duration
  centered 1/3/7/14-day windows and a raised-cosine ±15/30/45/60-day seasonal
  reference. All calendar years touched by a target window are excluded from
  reference measurements and, where applicable, sensor-calibration fitting.
- Known global-outage days and archive/startup boundaries invalidate complete
  windows; they are never shortened or treated as zero. Statewide totals retain
  boundary cells; custom AOIs select cell centers. Reference ranks are
  retrospective, with at least ten comparison years, and are not p-values.
- All 59 tests pass, including 14 new activity tests covering month/year continuity, leap
  days, window support, tie/zero semantics, held-out years including New Year
  spillover, sensor-fit exclusion, historical estimates, reference sensitivity,
  boundary-cell retention, unavailable regions/windows and API validation.
- TypeScript check and static production generation pass. Prepared artifact
  hash matches the diagnostics provenance. A real-data cross-year smoke check
  confirms the 2020-12-28–2021-01-03 target excludes both 2020 and 2021.
- Known-benchmark checks compare MODIS and VIIRS targets against the same
  VIIRS-only seasonal reference. Seven-day active-cell score disagreement is
  51.31 points on average (5,977 active comparisons); outlier agreement at 95 is
  81.73%. This is too much disagreement for an established sensor-independent
  short-window score. VIIRS is the UI/API default. The MODIS-extended reference
  remains an explicit experimental option, with actual diagnostics and a
  reference-choice sensitivity comparison. See ACTIVITY_OUTLIERS.md.
- Browser checked the actual running application at port 3000: navigation,
  November/December and December/January measurement windows, historical MODIS
  reference, known-outage unavailable state, outlier-only filter, observation
  overlay, cell popups and JSON export. Downloaded JSON parses with method,
  calibration provenance and all 224 statewide cells.
- Desktop 1440×1050 and mobile 390×844 layouts inspected; mobile document width
  equals viewport width. Browser error log was empty. Temporary viewport changes
  were reset. The separate production-build QA server was stopped; the existing
  development frontend remains, with its project API refreshed on port 8000.
- Screenshot: screenshots/seasonal-outliers.png. No cloud deployment performed.

## Event-based seasonal outliers v2 (2026-11-15)

- Default outlier view now uses inferred same-sensor spatiotemporal activity
  tracks and fixed local 10 km comparison areas, with separate occurrence and
  conditional-positive activity scores. Original cell comparison remains available.
- User requirement is explicit: first recorded local events retain occurrence
  100 and outlier status, including short archives, insufficient seasonal
  reference years, and regional support for strength. A positive report on an
  incomplete historical day still counts as prior activity; gaps cannot erase
  evidence and manufacture a first occurrence.
- All **91 current tests pass**, including 16 event tests covering tracking
  identity/singletons, own-event rather than neighboring-event counts, conditional
  ranks/ties, preserved novelty, regional pooling, archive/gap support, same-event
  reference exclusion across years, bbox/API validation and prepared-artifact
  hash-pair rejection. The larger count includes unrelated existing harmonization
  tests present in the shared checkout; no harmonization implementation changed.
- TypeScript and static production generation pass. Runtime event preparation
  contains 95,039 inferred tracks from 1,169,069 eligible detections; metadata
  and track artifacts are hash-linked to the observations and each other.
- Fixed known-case audit covers seven dates and 1,484 earlier perimeter examples.
  All first-recorded cases stay flagged. Among previously flagged small records,
  median source-perimeter share changes from 33.3% to 44.4%; attribution ambiguity
  remains substantial. A 125-row review sheet is prepared with human judgments
  blank. These diagnostics are not independent human validation or precision/recall.
- Browser verified the running localhost:3000 application: new default/old cell
  view toggle, separate score coloring and filters, event/point popups, first-recorded
  score 100 alongside activity 50, known-outage unavailable state, and JSON export.
  Downloaded export has 42 events and preserves both first-recorded outliers for
  18 January 2014. No browser console errors observed.
- Desktop 1440×1050 and mobile 390×844 layouts inspected; mobile document width
  equals viewport width. Temporary viewport override reset. Screenshot:
  screenshots/event-outliers-v2.png. Local API refreshed on its existing port;
  no cloud deployment performed.
- Method, known-case results and limitations: EVENT_OUTLIERS_V2.md.
