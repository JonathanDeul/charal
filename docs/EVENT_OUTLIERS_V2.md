# Event-based seasonal outliers — v2, 15 November 2026

The default **Seasonal outliers** view now shows inferred observed activity
**events**, with separate **occurrence** and **activity** scores. The original
0.5° cell view remains available through “Original cell comparison.” Both use
moving seasonal reference windows rather than calendar-month cutoffs.

## User requirement: first observed activity remains an outlier

If no earlier retained observation from another event exists in the same local
comparison area, the occurrence score is **100** and the event stays an outlier.
This also holds when later reference years contain activity, the archive is
short, fewer than ten reference years are usable, or the activity-strength
component borrows regional support. Reference support is displayed separately;
it never discounts this novelty or filters it away.

“First recorded locally” means first in the **selected satellite archive** and
within the fixed local comparison area. It cannot establish that a region never
burned before the archive or during missed/cloudy observations. The target
inferred event's own earlier detections are excluded when looking for a previous
*different* event. A first event remains novel throughout its observed track.

If historical seasonal comparison windows are all zero, occurrence likewise
scores 100, even when another event occurred in a different season. If no
eligible seasonal reference can be estimated, an archive-novel event still has
occurrence 100; its seasonal frequency and strength may remain unavailable.

## Observation tracks and spatial support

The offline preparation links occupied **1 km** cells belonging to the same
sensor if their centers are within **3 projected km** and their UTC dates are
at most **two days apart**. Connected components form deterministic activity
tracks. Isolated observations are retained. MODIS and VIIRS identities are
separate; sensor observations are never summed merely because both are present.
The prepared snapshot contains **95,039 tracks**, of which 4,934 have a
retrospective CAL FIRE perimeter/date overlap.

These are inferred tracks, not verified incident identities. Nearby fires can
merge, separate parts of a large incident can form several tracks, and gaps can
split tracks. Full-archive connectivity is retrospective; no causal real-time
tracking or fire-spread forecast is claimed. The thresholds are explicit
prototype choices, not fitted universal fire-identity parameters.

For each track active in the measurement window:

1. Find its densest occupied 1 km cell in that **current window**, without using
   future spread to choose its comparison location.
2. Use a fixed **10 km radius** around that cell's center for target and reference.
3. Count only that event's observations inside this support for its target
   activity; other simultaneous events do not contribute to its count.
4. Retain the full current event observation count as an additional displayed
   field. The component scores describe its representative local part, not all
   activity over the entire extent of a very large fire.

Distances and support disks use the same spherical Lambert cylindrical equal-area
projection as the map's activity grid (standard parallel 37.5°N); physical distances
are approximate. Leaflet circles illustrate comparison support, not burn scars.
The historical acquisition mask still clips observations to California; border
support may extend beyond the prepared archive. Custom AOIs select tracks with
at least one source observation in the current window inside the AOI. The track
and its comparison area remain whole rather than being clipped to that AOI.

CAL FIRE names are **overlap labels**. They are attached offline from an actual
point-center-in-perimeter match during its alarm/containment interval. A track
can overlap multiple records, complexes or fragments; the displayed label uses
the largest linked count. Labels do not certify that every observation belongs
to one independently identified incident.

## Two-part seasonal calculation

Measurement durations remain centered **1/3/7/14 days**. Seasonal windows remain
**±15/30/45/60 days**, with raised-cosine weights on the cyclic leap-year calendar.
Reference years have equal total weight. The complete target measurement years
are excluded, as is every reference window overlapping any observation date of
the same inferred track, including its observations in adjacent years.

A historical comparison value is the **largest single-event activity** within
the same disk and duration. It does not sum neighboring historical events into
one larger synthetic event. This provides a consistent single-event reference
for the target event's own count.

- **Occurrence:** 100 × the year-balanced seasonal fraction of reference windows
  with no activity. Archive novelty overrides this to 100, as specified above.
  The un-overridden seasonal occurrence value remains in the export as
  `seasonal_occurrence_score`.
- **Local activity strength:** the weighted midrank of the target event's count
  among **positive** historical reference values. Zero windows are excluded.
  Without positive reference values, this local strength is unavailable.
- **Regional strength support:** if fewer than three local active reference
  years exist, the positive-count ranks from four equally sized disks centered
  30 km east/west/north/south can contribute. Each available disk contributes
  equally. Mixing weight is `(3 - active_local_years) / 3`, clipped at zero;
  no local positive reference means full regional support if any exists.
  **Only strength is pooled. Occurrence and novelty stay local and unchanged.**
- **Outlier:** either component reaches the selected threshold (95 or 99).
  Both component values and the reason are displayed; no calibrated combined
  probability or new single overall percentile is claimed.

This is an empirical two-part/hurdle-style decomposition with explicit positive
reference mixing, not a fitted Poisson/NB model or a Bayesian hierarchical fit.
Regional areas are geographically nearby comparison supports; their ecological
comparability has not been independently validated. Land-cover covariates are
not silently assumed to exist. Borrowed strength is explicitly labeled in the UI.
The structural separation of zeros/positives is consistent with the description
of [hurdle count models](https://www.statsmodels.org/stable/examples/notebooks/generated/count_hurdle.html).
Event tracking as a general strategy is described by the
[NASA/UCI Wildfire Tracking Lab](https://earth-information-system.github.io/fireatlas/docs/);
this prototype is not an implementation or validation of their FEDS algorithm.

## Reference support and sensor limits

The UI reports reference years, active local reference years, prior archive
length, regional strength weight, and changed classification under shorter/
longer seasonal reference windows. Fewer than three prior archive years or
three local active reference years produces a “Limited support” label. This
label does **not** lower a score, hide a first occurrence, or reject a single
observation. Seasonal sensitivity is a descriptive check, not a confidence
interval. No numeric guarantee of physical fire probability is claimed.

At least ten eligible reference years are required for ordinary seasonal ranks.
An archive-novel occurrence remains flagged when that rank is unavailable.
Known-outage, startup and archive-boundary measurement windows are unavailable
rather than shortened or set to zero. Unknown cloud/exposure gaps remain.

VIIRS is the default. The experimental longer reference uses calibrated MODIS
before 1 February 2012 and observed VIIRS thereafter. Historical MODIS weights
use the separate smooth daily calibration and its target-year exclusions.
Neither event identities nor two-part scores across this sensor transition
have been independently validated. Missing small fires cannot be reconstructed.

## Known-case audit and review set

`scripts/audit_event_outliers.py` fixes seven dates spanning winter/summer,
ordinary and extreme activity, before computing the follow-up metrics. They
are already-known development cases, not a pristine test:

| Anchor | Observed tracks | Outliers (either component) | First recorded locally |
| --- | ---: | ---: | ---: |
| 18 Jan 2014 | 42 | 10 | 2 |
| 14 Aug 2014 | 57 | 12 | 2 |
| 1 Sep 2017 | 75 | 28 | 0 |
| 11 Nov 2018 | 64 | 21 | 0 |
| 15 Sep 2020 | 74 | 42 | 0 |
| 21 Jun 2021 | 71 | 21 | 1 |
| 10 Jan 2025 | 127 | 48 | 0 |

All archive-novel events in these snapshots retain occurrence 100 and outlier
status. The audit also revisits the 1,484 perimeter examples from the previous
analysis at the same peak-week anchors. Among the 222 previously flagged small
(<100 ha) records, 220 retain matched observations in the new representative
support. Their median share of detections spatially/temporally associated with
their own perimeter changes from **33.3%** under the old cell comparison to
**44.4%** under the new event/support comparison. The fraction below one-half
changes from 71.2% to **50.9%** (new denominator 220). Two records have no matched
point in the representative disk of their selected track. These are diagnostics
of attribution and remaining ambiguity, not precision/recall or independent proof
of true event identity. Tracking still leaves substantial ambiguity.

The fixed [review sheet](../data/research/event_outliers_v2/review.csv) has 125
rows spanning first occurrences, occurrence-only, activity-only, both and
unflagged events. Human judgments are blank. This makes a concrete review set
available without inventing expert labels or claiming validated scientific
alarm quality. Review must precede any claim of human-evaluated precision/recall.

Examples in the new local supports: Soda 2014 has occurrence/activity 100/100;
Palisades on 10 January 2025 has 99.74/100; Eaton has 98.50/100. Their target
supports and units differ from the old 0.5° method, so score changes alone do
not measure improvement.

## Reproduction and runtime

```sh
.venv/bin/python scripts/prepare_fire_events.py
.venv/bin/python scripts/audit_event_outliers.py
.venv/bin/python -m pytest tests -q
npm --prefix frontend run typecheck
npm --prefix frontend run generate
```

Preparation requires the packed observations and full perimeter source snapshot;
Shapely is an offline dependency. Runtime adds only `activity_events.npz` and
`activity_events.json` to the existing prepared assets. The JSON records source
hashes; the API rejects a mismatched observation artifact. Restart the API after
replacing prepared assets because prepared arrays and scored selections cache.

`GET /api/event-outliers` accepts the date/window/season/reference/threshold/bbox
parameters of the cell endpoint plus `include_points`. It exports both scores,
reasons, source overlaps, support and sensitivity, rather than discarding any
component into one opaque value. `/api/activity-outliers` remains the original
cell baseline. Event JSON export is available from the new view.
