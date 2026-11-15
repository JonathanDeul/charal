# Seasonal activity outliers — 15 November 2026

The [v2 event method](EVENT_OUTLIERS_V2.md) is now the default view. This document describes the original cell baseline, retained through “Original cell comparison.”

The **Seasonal outliers** page answers: “How unusual is reported activity here
for this time of year?” It does not score perimeter size or an individual
fire's physical severity. Clicking a detection exposes its surrounding cell's
activity score.

## Measurement and historical comparison

- Fixed 0.5° California-intersecting cells, derived from the independent Census
  boundary, including cells with no recorded detections. The full state uses
  all 224 cells, including boundary cells whose centers lie beyond the state
  bbox. Custom regions select cell centers; areas without a center are unavailable.
- Real daily eligible FIRMS detections are counted by center. No monthly count
  is spread over invented days. The source observations and quality rule are
  the same as the existing map.
- The measurement is a centered **1, 3, 7 (default), or 14 day** total. For an
  even duration, the extra day follows the anchor. The seven-day window anchored
  on 30 November runs from 27 November through 3 December, inclusive UTC.
- Historical comparison anchors lie within **±15, 30 (default), 45, or 60
  calendar days**, across other years. The same measurement length applies to
  every historical anchor. Season distance wraps across December/January.
- A leap-year month/day template gives a common 366-position calendar: March 1
  has the same position in every year; February 29 has its own position.
- Seasonal weight at distance `d < radius` is
  `0.5 * (1 + cos(pi*d/radius))`; it is zero at/outside the radius. There is no
  month boundary and no abrupt cutoff in weight at the seasonal-window edge.
- Each eligible reference **anchor year** is normalized to total weight one.
  At least ten reference years are required. Every calendar year touched by the target measurement
  is excluded, as is every candidate measurement window touching those years,
  including windows centered in adjacent years. This also excludes target-window
  spillover across New Year.
- Known sensor-outage days invalidate every measurement window containing
  them. Windows outside the archive or before VIIRS startup are unavailable,
  never shortened or filled with zero. No listed outage does not establish
  complete/cloud-free observation exposure.

The score is `100 * (weighted fraction below target + 0.5 * tied weight)`.
Zero target activity is assigned score zero for this upper-activity score.
A score of 100 is a finite-reference rank: all comparison windows are lower.
It is not a p-value, probability of danger, or return-period estimate. Adjacent
and overlapping windows are correlated; 1,000 reference windows do not mean
1,000 independent fires. The weighted median and the number of years/windows
are shown. This first version compares the same cell across seasons/years;
it does not borrow observations from neighboring cells or estimate a rare-tail
parametric distribution. The selected-area score first sums daily activity
across its cells, then ranks the regional total; cell percentiles are not summed.
The reference is retrospective and fixed through 2025, rather than controlled
by the calendar's year-display filter. It describes historical rarity, not a
trend-adjusted present-day fire regime or a prospective forecast.

## Sensor reference and empirical check

**Default: observed Suomi-NPP VIIRS, 2012–2025**, subject to startup/outage
windows. **Optional: experimental MODIS + VIIRS, 2001–2025.**

The optional extension is a separate daily calibration. It fits smooth
calendar-day VIIRS/MODIS ratios from pooled statewide training totals in
2013–2020, with the same ±30-day raised-cosine kernel. These ratios multiply
actual daily MODIS cell counts. It uses MODIS estimates through 31 January
2012 and observed VIIRS from 1 February onward. Sensors are never added in the
scientific activity series. All calendar years touched by the target measurement are also excluded from
the ratio fit when they fall in the training period. The existing monthly calendar and estimator are unchanged.

`scripts/audit_activity.py` fixes anchor spacing at 14 days and reports the
already-inspected 2021–2025 period as a **known benchmark**, not a pristine test.
Ratios use no benchmark-year measurements for fitting. Scores for MODIS and
VIIRS target measurements use the same VIIRS reference, excluding every year touched by the target
measurement. Benchmark measurement windows lie wholly within 2021–2025. Active comparisons have positive reports in either sensor. All eligible
cells are retained for count-error metrics, including zeros.

| Measurement window | Active comparisons | Mean absolute score difference | Agreement at score ≥95 | Cell-window count WAPE |
| --- | ---: | ---: | ---: | ---: |
| 1 day | 1,757 | 64.24 points | 61.01% | 51.74% |
| 3 days | 3,500 | 59.21 points | 74.60% | 43.58% |
| 7 days | 5,977 | 51.31 points | 81.73% | 34.35% |
| 14 days | 8,300 | 44.81 points | 85.40% | 26.87% |

These discrepancies are too large to treat the longer series as an established
short-window anomaly reference. Missing small MODIS detections can make ranks
very different even when monthly regional totals are calibrated reasonably.
The longer reference therefore remains an explicit experimental option, with
its actual benchmark error displayed. A second score compares the **same target
activity** with the VIIRS-only reference; changed outlier classification is
marked “sensitive.” That comparison isolates reference choice. It is not an
uncertainty interval and cannot resolve the true historic activity.

Residual bands from the monthly calendar are not reused as daily probabilities.
No complete propagation of historical calibration error is claimed. Early
Terra-only sampling, processing versions, orbit drift and unmeasured local
exposure remain limitations. Both reference choices remain exploratory ranks.

## Reproduction, API and export

```sh
.venv/bin/python scripts/pack_data.py
.venv/bin/python scripts/prepare_activity.py
.venv/bin/python scripts/audit_activity.py
.venv/bin/python -m pytest tests -q
npm --prefix frontend run typecheck
npm --prefix frontend run generate
```

The preparation uses packed observations, `coverage.json`, and the original
`data/raw/california_census2020.geojson`; Shapely is an offline preparation
dependency. The deployed API needs only the compact `activity_daily.npz`,
`activity_metadata.json`, and `activity_diagnostics.json` additions. Original
input hashes and calibration configuration are recorded in metadata. Regenerate
all three after changing sources or calibration; restart the API after replacing
prepared data because it caches its arrays and selected results.

`GET /api/activity-outliers` accepts `anchor_date`, `window_days`, `season_days`,
`reference=viirs|harmonized`, `threshold`, and optional `bbox`. It returns cell
scores, regional score, dates, source status, reference support, reference-choice
sensitivity, method, input provenance and diagnostic results. Invalid dates,
unsupported windows/references and invalid bbox/thresholds are rejected.
The page's **Export scores & method** downloads this complete JSON response.
Raw points are an optional uncalibrated overlay; their popups report cell context,
not an inferred assignment to a distinct fire.
