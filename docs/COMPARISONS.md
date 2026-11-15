# Historical year and event comparisons

The data snapshot remains frozen through **31 December 2025**. There is no live feed.

## Compare years

The Fire calendar includes an annual bar ranking and a two-year monthly overlay.
The selected region and global year range apply. The default reference is observed
Suomi-NPP VIIRS, with annual comparisons starting in 2013. The optional harmonized
reference uses the current production calendar, including modeled history from 2001.

An annual total and rank require all twelve eligible monthly values. A listed
VIIRS outage, startup year, missing month or unsupported spatial selection must
not appear as low annual activity. Incomplete years stay unranked; monthly gaps
remain null in the overlay. Annual percentage differences require two complete
years and a nonzero denominator. Tied totals share a competition rank. No monthly
residual or bootstrap interval is summed into a fabricated annual interval.

The units are reported or harmonized reference-scale satellite detections,
not fire count, burned area, duration, physical severity or total emitted energy.
A zero is a report count, not evidence of no fire. Cloud and sampling effects
remain even without listed outages. Calibration does not ensure physical sensor
equivalence or validate pre-VIIRS activity directly.

`GET /api/compare-years` takes `start_year`, `end_year`, `bbox` and
`reference=viirs|harmonized`. The panel exports the response as JSON.

## Compare a fire

The new navigation entry opens a historical cutoff selector (2013–2025) and
up to 100 VIIRS tracks with most detections during the preceding seven days,
including the cutoff, within the selected region. Click a map marker or a visible
event card to choose a track; the most active track is selected automatically.
The optional name filter narrows the list. Markers use the mean location of
recent, region-selected detections through the cutoff, not later observations. All activity comparisons use observed Suomi-NPP VIIRS only. MODIS-derived
single-event histories are not treated as established equivalents.

An event is a prepared connected observation track, not a confirmed incident.
The onset is its first VIIRS detection. The target's cumulative count uses only
reports from onset through the cutoff, inclusive, at most 366 UTC dates. The
selected-area filter selects tracks; comparison counts cover each entire track.
No post-cutoff detections contribute to target counts, curves or locations.

Eligible references:

- Start in 2013 or later, in a year preceding the target onset year.
- Have the same number of observation days as the target. The whole comparison
  interval must end before the target onset year.
- Start within ±60 circular calendar days of target onset (leap-year calendar),
  and within 300 km in the existing equal-area projection, measured between the
  tracks' first detections.
- Have no listed VIIRS outage in that whole interval. A gap in the target
  interval makes its comparison unavailable. Observation days after a reference
  track ends still count toward the equal-length interval; zero reports do not
  establish physical inactivity.

The finite-reference midrank is 100 × (fraction of totals below the target +
half the tied fraction), across **all** eligible reference tracks. Five example
tracks minimize mean absolute difference between `log1p` cumulative count curves.
The UI reports eligible tracks, distinct years, spatial/seasonal offsets and
counts at equal age. Examples are descriptive nearest matches, not forecasts.
The pool contains many small tracks and is not incident- or year-balanced;
a high rank is not an independent tail probability or a danger assessment.

Track connectivity and CAL FIRE name associations were prepared from the full
archive and may therefore use later information. This is explicitly retrospective,
not a reconstruction of the identity that would have been known live. Nearby
fires may merge, observation gaps may split fires and complexes may recur under
several track IDs. No final perimeter area is assigned to the partial history.

`GET /api/compare-fire?as_of=YYYY-MM-DD&bbox=...` lists tracks.
Adding `event_id` returns the equal-age comparison. The event panel exports its
response and method as JSON. Its reference always uses eligible earlier years,
independently of the global calendar display-year filter.

## Verification

`tests/test_comparisons.py` covers annual gap/startup policy, equal-age counts,
exclusion of future observations and years, missing target/reference windows,
and region/date selection. `tests/test_api.py` covers route validation.
