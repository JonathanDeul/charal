# Charal — submission draft

Working project title: **Charal: A More Continuous History of Fire**

Challenge: Harmonization of MODIS and VIIRS Hot Spots.
Study area: California, USA. Snapshot: 2001–2025.
Team/event: user to add the actual team name, team-page link, Cambridge event details, and eventual public demo/code URLs. No project page or external submission has been posted.

## Short project summary

Charal connects 25 years of California fire observations across two satellite generations. An interactive burning calendar, linked hotspot map and historical comparisons help users explore when and where activity has changed. We train and evaluate a sensor-calibration model against simple baselines, preserve known data gaps, and test whether documented wildfire areas follow a power law. The result is a transparent research tool: 1.17 million quality-filtered NASA detections, independently mapped CAL FIRE perimeter records, downloadable evidence, and explicit uncertainty.

## The problem

More detections do not always mean more burning. MODIS and VIIRS differ in spatial resolution, sensitivity, sampling and processing history. Combining their counts directly can make a sensor change look like an environmental trend. A useful historical calendar must keep those differences visible while building a defensible common scale.

## Our solution

Charal has three linked investigations:

1. **Observe:** Select a region and period, inspect a 25-year monthly calendar, and click a month to see the associated satellite detections. Compare that month's harmonized activity with the median for the same month in other selected years.
2. **Harmonize:** Aggregate MODIS and Suomi-NPP VIIRS on a shared 0.5° monthly grid. Compare a trained Poisson-loss boosted-tree model with a seasonal count-ratio baseline and a seasonal climatology. Select the method on validation years, then report untouched future-year and geographic holdout results.
3. **Test extremes:** Use documented CAL FIRE perimeter areas to estimate a tail threshold, fit a power-law hypothesis, bootstrap its compatibility, and compare conditional lognormal and exponential alternatives. Test sensitivity to linked/named complex records.

Known incomplete observation months remain unavailable. Observed points are never invented to fill a sensor gap. Every analysis can be exported with its selection and provenance.

## What makes this approach useful

The tool connects visual exploration to tests that can disprove an appealing idea. In this study, the simple calibration generalizes better than our ML candidate; the app uses the better validation-selected method and reports both. The documented fire-area sample is broad, but a simple power law is rejected. These are useful results: they show why observational bias, baselines, alternative distributions and reporting completeness belong inside an analytical tool.

## Actual results

- 1,315,630 original California hotspot detections from 39 official annual NASA files.
- 1,169,069 detections after the declared type/confidence rule.
- 8,699 CAL FIRE perimeter records; 1,966 meet the 300-acre tail-analysis floor.
- Training 2013–2020; validation 2021–2022; future test 2023–2025. Independent NASA outage flags leave 31 clean test months.
- Test monthly MAE: 291.33 for ratio calibration, 513.29 for trained boosted trees, 3516.66 for the seasonal mean. Baseline WAPE 13.21%; ML WAPE 23.27%.
- Seventeen known-incomplete calendar months are masked rather than interpreted as low burning activity.
- Main tail fit: α≈1.544, x_min≈130.6 ha, 1,918 tail records; bootstrap p = .005 over 199 replicates. Conditional lognormal has higher likelihood. Complex-record sensitivity preserves rejection of a simple power law.

Do not describe the ML model as beating the baseline, the distribution as a confirmed power law, the calibration as perfect sensor equivalence, or perimeter records as guaranteed independent fires.

## Data and resources

- NASA FIRMS/LANCE/Earthdata historical country archives: https://firms.modaps.eosdis.nasa.gov/download/
- FIRMS Standard Data missing-date metadata: https://firms.modaps.eosdis.nasa.gov/api/missing_data/
- CAL FIRE FRAP historical wildfire perimeters: https://data.ca.gov/@cal-fire/california-fire-perimeters-all
- US Census Bureau TIGERweb 2020 state/county boundaries: see exact queries in MAP_DATA.md and DATA_SOURCES.md.
- Clauset, Shalizi & Newman (2009), *Power-Law Distributions in Empirical Data*: https://doi.org/10.1137/070710111
- Drossel & Schwabl (1992), *Self-organized critical forest-fire model*: https://doi.org/10.1103/PhysRevLett.69.1629
- Pruessner & Jensen (2004), scaling limitations: https://doi.org/10.1103/PhysRevE.70.066707

Credit NASA FIRMS/LANCE/Earthdata, CAL FIRE FRAP and its cooperating agencies, and the US Census Bureau. Cite the source releases and processing caveats, including mixed MODIS version fields.

## Technology and AI-use disclosure draft

Frontend: Nuxt, Vue, Tailwind CSS, Leaflet, Lucide icons, SVG charts.
Backend/science: Python, FastAPI, numpy, pandas, scipy, scikit-learn and shapely.
Prepared regional datasets and statistics are served without runtime AI or LLM API calls.

**Disclosure draft:** We used OpenAI Codex, including cooperating research agents, to assist with source research, code generation, data-pipeline implementation, statistical analysis, testing, interface design and drafting project documentation. We trained a scikit-learn boosted-tree calibration candidate on declared historical training years. Held-out model scores and empirical findings are reported, including results that did not support our original hypotheses. Human team members should review the implementation, scientific interpretation and submission text before submission.

Adjust this disclosure to the actual team workflow and the current submission form's wording. Do not claim human review that has not occurred.

## 60–90 second demonstration script

**0–15s — Problem:** “A satellite change can look like a change in fire. Charal asks how we can connect25 years of observations without hiding the measurement process.”

**15–35s — Calendar and map:** Show all California, 2001–2025. Select September 2020. “This month has 125,290 quality-filtered Suomi-NPP detections—about 20 times the median September in the other selected years. These are detections, not 125,290 separate fires.” Select Northern California or draw an area and show linked updates.

**35–50s — Missing data:** Select July 2024. “NASA lists sensor outages. We mark this month's harmonized activity unavailable instead of turning missing observations into a quiet fire season.”

**50–65s — ML:** Open Sensor harmonization. “We trained boosted trees and tested against simple controls. The ratio model performed better on validation and future years. The tool shows that evidence and uses the selected method.”

**65–80s — Power law:** Open Extreme fires with the full state and period. “We also tested whether large mapped fire areas follow a power law. The simple hypothesis is rejected here; lognormal fits better. Scientific tests, not a straight line alone, guide the interpretation.”

**80–90s — Value:** “Explore, compare, and export a traceable fire history. A regional proof of concept now; broader sensors, observation-opportunity corrections and an explanatory Drossel–Schwabl experiment next.”

For a shorter local pitch, emphasize the problem, linked calendar, and transparent findings. Confirm permitted demo/video length with the actual Cambridge event instructions.

## Seven-slide pitch outline

1. **The measurement problem:** Two instruments; a long historical question; raw counts are not directly comparable.
2. **Who needs a continuous record:** Land managers and researchers comparing seasons and unusual periods in a selected region.
3. **A working California observatory:** Calendar, map, AOI, period selection, anomaly comparison and exports.
4. **Harmonization with evidence:** Shared cell-months, one VIIRS reference, baselines, held-out evaluation, known-gap masking.
5. **Extremes as a testable question:** Event-area observable, tail threshold, alternatives, bootstrap and complex-record sensitivity.
6. **What we learned:** Baseline beats current ML; pure power law rejected; transparent limitations improve interpretation.
7. **What comes next:** Consistently reprocessed records, coverage/overpass correction, additional regions, prospective ML validation, optional cellular-model/sensor-sampling experiment.

## Before pressing Submit

Add team details, verify Cambridge's actual local timetable, supply accessible demo/code links if required, adapt fields to the current official project form, credit data/tools, disclose AI assistance, and review scientific claims. The app, documentation and prepared deployment do not constitute an official submission. No external message or submission has been made.
