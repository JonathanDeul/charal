# Scientific methods and interpretation

This document describes the original production analysis (v1). The separate [15 November harmonization v2 experiment](HARMONIZATION_V2.md) adds model families and western-US data after the original test results were known. It uses a frozen follow-up protocol and labels 2023–2025 as a known benchmark. Its regional safeguards rejected promotion, so the production estimator and original analysis below remain unchanged.

The later [daily spatial/temporal context comparison (v3)](HARMONIZATION_V3.md) adds matched contextual boosting/CNN inputs, CAL FIRE event-boundary purging and a buffered transfer diagnostic. It is a separate exploratory study with no production replacement. Its fitting population differs from v1; the previously inspected periods remain explicitly labeled.

[V4](HARMONIZATION_V4.md) restores the original fitting population for direct comparison and finds a two-stage boosted candidate with better forward statewide, regional and overall cell metrics. Its full search, post-selection audits and failures are reported separately; repeated historical evaluation is not an untouched test. Candidate predictions do not replace the production calendar or inherit its residual bands.

The subsequent [neural/MPS comparison](HARMONIZATION_NEURAL.md) reaches the exploratory 2021–2022 monthly-MAE target <500 with a fixed three-seed numeric-embedding MLP ensemble. It preserves original fitting years and outage policy, selects epochs on2019–2020, and explicitly reports the adverse local/northern/backward metrics as well as all Transformer failures. Repeatedly inspected periods do not provide independent prospective confirmation, and the neural candidate is not promoted into the calendar.

This proof of concept addresses two different questions for California, 2001–2025:

1. How much of the apparent change in **reported hotspot detections** is associated with changing sensors, and how well can an empirical calibration reproduce one reference reporting scale?
2. What distributions are compatible with the **documented final areas of wildfire events**, above a reporting-size floor?

These questions use different observables. A hotspot is a reported thermal-anomaly pixel at a satellite overpass. A wildfire perimeter is a documented event boundary. Neither is an exact measurement of the number of burning fires or the precise area actually burned. See [NASA's interpretation of a fire detection](https://forum.earthdata.nasa.gov/viewtopic.php?t=5155) and [NASA's FIRMS caveats](https://forum.earthdata.nasa.gov/viewtopic.php?t=5188).

The separate [seasonal activity outlier method](ACTIVITY_OUTLIERS.md) uses real daily measurement windows and a smooth seasonal reference across years. It does not reuse monthly counts as daily observations.

## 1. Observational harmonization

### Reference and scope

The reference is **Suomi-NPP VIIRS 375 m hotspot detections**, counted in fixed 0.5° latitude/longitude cells by calendar month. MODIS combines its Terra/Aqua detections on their original reporting scale. NOAA-20/21 VIIRS detections are not added to Suomi-NPP; doing so would introduce a new sampling jump as satellites are added.

The California boundary clips the original point data. Candidate grid cells extend from 125°W to 113.5°W and 32°N to 42.5°N; cells that intersect the independently sourced California boundary are retained. A grid cell's existence therefore never depends on a future fire. Border cells preserve reports inside the state even when their centers lie just outside its boundary. The equal-angle grid does not imply equal physical cell areas, so the output is **count per cell-month**, not an area-normalized fire density.

Monthly records through January 2012 use a MODIS-derived estimate. From February 2012 onward the displayed harmonized series uses observed Suomi-NPP VIIRS reports. January 2012 is partly available and is flagged as a partial raw-reference month; its full-month harmonized value remains modeled. Archive start dates are documented by [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/download/).

### Models and controls

The learned candidate is scikit-learn's `HistGradientBoostingRegressor` with Poisson loss, 180 boosting iterations, learning rate 0.065, at most 15 leaves, at least 35 samples per leaf, L2 regularization 2, and random seed 42. It predicts nonnegative VIIRS-equivalent reported counts from features available on the historical MODIS side:

- MODIS count and `log(1 + count)`;
- `log(1 + summed FRP)` and mean reported MODIS FRP;
- fraction of MODIS reports acquired in daytime;
- cell-center latitude and longitude;
- sine and cosine of calendar month.

FRP is fire radiative power, not burned area or a measure of event count. Calendar year and VIIRS-derived measurements are excluded from predictors. No synthetic historical hotspot coordinates are created.

Research and runtime data share one eligibility predicate: `type == 0` (presumed vegetation fires, which include agricultural burning), MODIS numeric confidence at least 30, and VIIRS nominal/high (`n`/`h`) confidence. The threshold classes are sensor-specific quality filters, not numerically comparable calibrated probabilities. Archived product-version strings are preserved. The prepared MODIS archive contains different version strings across the historical record, so it must not be described as a uniformly reprocessed Collection 6.1 series.

Two controls make the comparison meaningful:

- **Seasonal sensor-ratio baseline:** for each month of the year, divide training-period total VIIRS count by total MODIS count; multiply each MODIS cell count by that ratio. When a month's denominator is zero, use the global training ratio.
- **Seasonal climatology:** each cell's mean VIIRS count for that calendar month in the training years, without MODIS input. This tests whether the learned model adds information beyond ordinary seasonality and location.

### Held-out evaluation and selection

| Role | Complete years | Use |
|---|---|---|
| Training | 2013–2020 | Fit the ML candidate, sensor ratios, and climatology |
| Validation | 2021–2022 | Select ML or sensor-ratio baseline by lower statewide monthly mean absolute error; estimate residual bands |
| Test | 2023–2025 | Disclose all three methods' errors without changing selection or fitting |

The deployed/backcast estimator retains the original training fit. Validation and test years are not used to refit it. Repeated observations of one wildfire may occur across nearby cells and months, so a random row split would leak information; entire years are held out instead.

An independent quality policy excludes a paired month from training, validation and test if the [official FIRMS standard missing-data table](https://firms.modaps.eosdis.nasa.gov/api/missing_data/) lists any missing day for either participating MODIS platform or Suomi-NPP VIIRS in that month. The list comes from NASA, not from observed prediction errors. Exact eligible/excluded month lists and sample sizes are saved. The originally computed all-report-month results are retained separately as `evaluation.all_reported_months`, so the effect of this quality policy is inspectable. No additional model family was introduced after those original test results were inspected.

Known-incomplete VIIRS reference months retain their raw partial report counts but have a null harmonized calendar value and `source = incomplete_reference`. Known-incomplete pre-VIIRS MODIS months likewise have null harmonized values and `source = incomplete_modis`. They must be drawn as missing/partial, never as zero activity. A month with a listed MODIS gap but no listed VIIRS gap can still use its observed VIIRS calendar count; it is excluded only from paired model calibration/evaluation. January 2012 startup days are tracked separately from official outage days.

The NASA table describes listed global outages, not all local/cloud/partial-day exposure limitations. “No listed gap” is therefore a metadata status, not a guarantee of complete observation. In addition, Terra operated without Aqua before mid-2002, and late-life orbit changes alter sampling; the empirical count calibration does not make every historical platform configuration equivalent.

Primary metrics are MAE, RMSE, weighted absolute percentage error (WAPE), and signed bias of **statewide monthly total detections**. Cell-month MAE is supplementary, because a large number of no-report cells can make cell-level error look deceptively small. WAPE divides the total absolute error by the total reported reference count and is more stable than averaging percentages of near-zero months.

A second diagnostic trains only on cells south of 39.5°N in 2013–2020 and evaluates cells at or north of 39.5°N in 2023–2025. It tests geographic extrapolation as well as a later period. It does not establish global transferability. The production model is selected only by statewide validation MAE; spatial and final-test diagnostics remain visible even when unfavorable.

### Residual bands

The historic statewide modeled series is accompanied by a band using the 80th percentile of the absolute **statewide monthly** errors in the validation years. Cell bands use the 80th percentile of absolute cell errors divided by `sqrt(prediction + 1)`, multiplied by `sqrt(current prediction + 1)`. Lower endpoints are clipped at zero.

These are **80% validation-residual bands**, not confidence intervals, not guaranteed predictive coverage, and not quantified uncertainty about true fire activity. They summarize retrospective disagreement with the reference reporting scale under a particular validation regime. They may miss historical distribution shifts. The number of eligible calibration months and actual eligible-test-month band coverage are reported. Cell bands must not be summed to form a regional uncertainty interval: neighboring cell errors are correlated. Observed VIIRS counts have no model band; this does not mean their physical measurement is error-free.

### Essential limits

- A zero count means zero reports in the acquired archive. Hotspot CSVs alone do not provide cloud-free observation exposure, complete orbit coverage, or proof that no fire occurred.
- The pipeline rejects a missing whole sensor-year instead of silently filling it with zeros. This check does not detect every partial-day or partial-month data outage.
- Differences in pixel geometry, overpass timing, sensitivity, orbit drift, clouds, smoke, land cover, and small-fire detection remain. Empirical calibration is not a complete physical observation model.
- Backcasting assumes the post-2012 relationship also applies before VIIRS existed. This assumption cannot be directly validated with VIIRS observations from those earlier years.
- Common-grid aggregation alone is not sensor harmonization. Its calibration and held-out results must be reported together.
- The app approximates user-selected areas by including cell centers inside the selection. A cell can straddle the selection boundary. The hotspot point export can use exact coordinate filtering, so raw exported counts and cell-center aggregate counts need not match.

### NASA map: pixel proxies and activity cells

The map is an **uncalibrated observation view**, separate from the 0.5°
count harmonization. VIIRS Suomi-NPP is the default; MODIS Terra/Aqua and both
sensors can be selected. No synthetic historical footprints are inferred.
The new `/api/fire-map` endpoint retains every eligible observation in the
selected month/day and center-selected bounding box, without sampling.

Pixel footprints are approximate north-aligned rectangles using FIRMS
`scan` and `track` dimensions in kilometers around the pixel center. They do
not include the scan orientation or exact geolocated corners, do not clip to
coastlines, and are **not burned-area polygons**. The display uses 111.195 km
per latitude degree and the latitude cosine for longitude. Overlapping
semi-transparent footprints can darken; their colors are not a union statistic.
The day selector uses UTC acquisition dates; individual details retain UTC time,
satellite, scan/track dimensions and pixel-integrated FRP in MW.

An optional 1 km grid uses a spherical Lambert cylindrical equal-area projection
(radius 6,371,008.8 m, standard parallel 37.5°N, fixed origin at 0°,0°).
Detections are assigned **by pixel center**, not by footprint intersection.
The filled cells represent spatial aggregation support, not detected pixel
boundaries. This grid is independent of the existing 0.5° harmonization grid.
Each cell reports distinct UTC dates with detections, first/last detection
dates, observation count, sensor membership, and the maximum valid reported
pixel FRP. Multiple reports/sensors on one UTC date count as one detection day;
the span between first and last dates is not continuous fire duration.

Color modes show pixel FRP (or maximum pixel FRP per grid cell), detection days,
sensor, or a combined grid view with FRP color and opacity
`0.25 + 0.65 × (detection_days - 1) / 30`. Fixed color bins allow visual
comparison between selections, but do not correct sensor-dependent sensitivity
or pixel support. Combined mode is exploratory, **not FRP × duration**, total
energy, burn severity, or a harmonized area estimate. Missing FRP is gray;
invalid pixel geometry is omitted from footprints/points and explicitly counted,
while its center observation remains in grid statistics.

Only positive detections are available. Clouds, unobserved overpasses, partial
months and known outages remain; detection-day counts are not normalized by
clear-sky observation opportunities. Combining sensors changes those opportunities.
No detection is not evidence of no fire. No square-kilometer burned-area total
is calculated from these views.

## 2. Event-area tails and power laws

### Observable and eligibility

The input is the CAL FIRE FRAP historical **wildfire** perimeter archive for fires with start years 2001–2025. Prescribed burns are excluded by the selected source layer. The area unit is hectares; one acre equals 0.40468564224 hectares. Invalid/nonpositive areas, out-of-period records, and repeated stable identifiers are removed before fitting; acquisition provenance records additional source cleaning.

Current CAL FIRE reporting criteria vary with vegetation: at least 10 acres in timber, 50 in brush, or 300 in grass, with additional structure-impact and fatality conditions. Cooperating agencies currently submit perimeters of at least 10 acres. A common **300-acre (121.405692672 ha) lower floor** removes the obvious differences among those current vegetation-dependent cutoffs. It cannot guarantee uniform completeness in the historical archive. The archive explicitly documents missing records, duplicate fires, and perimeter generalization. Large perimeters can include unburned islands. See the [official CAL FIRE dataset metadata](https://data.ca.gov/@cal-fire/california-fire-perimeters-all).

The analysis remains conditional on **documented perimeter records above the stated floor**. A fit to these records is not automatically a fit to every California wildfire or to independent events. Mixed ecosystems, fire suppression, changing land use and reporting practices may all affect the tail.

A separate complex sensitivity subset excludes every record with a `complex_id` or `complex_name`, every name containing “COMPLEX,” and any record whose IRWIN ID is referenced as a complex parent. No records are automatically collapsed merely because they share an IRWIN ID. This conservative metadata-based exclusion tests whether the conclusion survives removal of known complex-related records; incomplete linkage metadata still prevents a guarantee of event independence.

### Estimation

For a continuous power-law tail beginning at `x_min`, the density is

`p(x) = (alpha - 1) / x_min * (x / x_min)^(-alpha)`, for `x >= x_min`, `alpha > 1`.

For a fixed threshold the maximum-likelihood estimate is

`alpha = 1 + n / sum(log(x_i / x_min))`.

The implementation chooses `x_min` by minimizing the two-sided empirical Kolmogorov–Smirnov distance between the fitted tail CDF and observations. It evaluates up to 80 deterministic observed-threshold candidates, plus the reporting floor, retaining at least 50 tail events. This finite grid is a computation compromise and is disclosed; 50 is a stability rule for the PoC, not a universal statistical guarantee. Degenerate or insufficient samples return an explicit unavailable result.

The graph is a complementary CDF: the empirical fraction of **tail events** with area at least `x`, conditional on being at or above the fitted threshold. The model curves are conditioned on the same threshold. The displayed `alpha` is the **density exponent**; the log-log CCDF slope is `1 - alpha`.

### Bootstrap and alternatives

The statewide artifact uses 199 semiparametric bootstrap replicates, random seed 42. Each replicate samples the number of tail events from a binomial distribution, resamples the empirical body below the fitted threshold, generates a Pareto tail, and **refits both the threshold and exponent** using the same algorithm. The compatibility p-value is `(1 + number of replicate KS distances >= observed KS) / (1 + successful replicates)`. A Monte Carlo standard error and the successful replicate count are saved. `alpha_ci` is the model-dependent 2.5–97.5 percentile interval of those refitted bootstrap exponents.

Separately, `alpha_empirical_ci` resamples the empirical perimeter records with replacement and refits the threshold/exponent on each replicate. It is an empirical percentile-bootstrap interval under an exchangeable-record assumption. Neither interval accounts for dependency among parent/child perimeters, unknown missing records, or changing reporting criteria. The fitted-model interval is especially conditional when goodness-of-fit rejects the model; it is not evidence that the fitted exponent describes a universal physical law.

A low compatibility p-value is evidence against this fitted tail model under this procedure. A larger p-value does not prove a power law. The small bootstrap count limits p-value resolution to about 0.005 and introduces Monte Carlo uncertainty.

The same tail is also fitted with:

- a lognormal distribution conditional on `x >= x_min`, maximizing the properly normalized conditional likelihood;
- an exponential distribution shifted by `x_min`, using its maximum-likelihood rate.

The artifact reports summed log-likelihood differences and approximate normalized two-sided likelihood-ratio diagnostics. Positive differences favor the power-law likelihood. These are exploratory comparisons with estimated parameters and a data-chosen threshold; the lognormal can approach a power-law-like tail at parameter boundaries, so its normalized-test p-value should not be interpreted as a definitive model-selection guarantee. Fits that cannot distinguish alternatives are labeled inconclusive.

An interactive subregion fit may omit the expensive bootstrap. In that case the app must display an exploratory fit, return null p-values and exponent intervals, and explicitly say that goodness-of-fit was not evaluated. Statewide bootstrap results must never be relabeled as evidence for a different subregion.

The statistical design follows the maximum-likelihood, goodness-of-fit, and alternative-comparison framework in [Clauset, Shalizi and Newman (2009), *Power-Law Distributions in Empirical Data*](https://epubs.siam.org/doi/10.1137/070710111). The implementation does not infer a power law from a visually straight log-log plot.

## 3. Optional Drossel–Schwabl extension

The model can become an educational experiment showing how growth, ignition and connectivity affect event-size distributions. A simplified observation layer could then reveal how one simulated fire pattern produces different apparent statistics at different sampling resolutions. This would explain the challenge's measurement problem.

It is not part of the validated calendar or a real wildfire-spread prediction. The original [Drossel–Schwabl model (1992)](https://journals.aps.org/prl/abstract/10.1103/PhysRevLett.69.1629) and [later large-scale investigations of broken scaling](https://journals.aps.org/pre/abstract/10.1103/PhysRevE.70.066707) also caution against treating a fitted exponent as proof of universal self-organized criticality.

## Reproduction

After acquiring the sources, use the project's locked Python environment and run:

```sh
python scripts/analyze.py --bootstrap 199 --grid 0.5
python -m pytest tests/test_science.py
```

The script writes `data/processed/analysis.json`, a local trusted production estimator at `models/harmonization.pkl`, and the trained boosted-tree candidate at `models/boosted_candidate.pkl`, even when validation selects the simpler ratio method. The generated JSON is the runtime data contract. Its input SHA-256 digests, provenance, selected estimator, split years, errors, fitted-tail parameters and limitations are inspectable. Training libraries are imported lazily; the web API only needs NumPy/SciPy for exploratory tail fitting and can serve the precomputed calendar without loading a pickled model.
