# Prepared California data snapshot

This proof of concept uses real public records. No synthetic hotspots or fire
events are included. The reproducible acquisition entry point is
`scripts/fetch_data.py`; file-level hashes, source versions, row counts, and
acquisition status are recorded in `data/provenance.json`.

## NASA active-fire detections

- **Source:** [NASA FIRMS Archive Download](https://firms.modaps.eosdis.nasa.gov/download/),
  via its [public annual country archive catalogue](https://firms.modaps.eosdis.nasa.gov/data/country/yearly_summary_files.txt).
- **Products:** MODIS Terra/Aqua annual standard-processing records,
  2001–2025; VIIRS Suomi-NPP 375 m annual records, 2012–2025. The public MODIS
  annual archive contains multiple processing version values, detailed below.
- **Country:** United States. Candidate points are first bounded by
  `[-124.5, 32.5, -114.1, 42.1]` (west, south, east, north), then clipped to the
  Census 2020 California state polygon. Candidate bbox records outside the state
  are excluded.
- **Archives:** one annual CSV per product, retained locally as a gzip file in
  ignored `data/raw/` for reproducibility. `data/processed/hotspots.csv` contains
  the state-clipped observations with their original provenance fields.
- **Fields:** latitude, longitude, acquisition UTC date/time, sensor, satellite,
  FRP (MW), confidence, day/night, product version, inferred thermal-anomaly
  type, scan/track pixel dimensions, and supplied brightness temperatures.
- **Duplicates:** exact acquisition/location/satellite/FRP duplicate records are
  removed; repeat overpasses and separate sensors are retained as observations.

The downloader preserves all thermal-anomaly types and all confidence classes.
Any subsequent vegetation-fire or quality filter must be described by the
analysis/API rather than silently modifying this source snapshot. The source
type codes are `0 = presumed vegetation fire`, `1 = active volcano`,
`2 = other static land source`, `3 = offshore`. These are inferred source
classes, not independently verified fire causes. Source confidence is an
algorithm-specific indicator and does not mean identical probabilities across
sensors.

The acquired snapshot has **1,315,630 state-clipped detections**: 319,822 MODIS
and 995,808 VIIRS. Of those, 317,044 MODIS and 913,719 VIIRS records have inferred
type 0 before any additional confidence or analysis-specific filtering.
All 39 requested annual files were acquired and their uncompressed sizes checked
against the official archive manifest. No exact duplicate acquisition records
were found by the downloader's defined key.

Observed MODIS CSV `version` values change within the record:

| Calendar years | MODIS CSV version value |
| --- | --- |
| 2001–2017 | `6.2` |
| 2018–2022 | `6.03` |
| 2023–2025 | `61.03` |

VIIRS CSV `version` is `2` throughout this acquired snapshot. These values are
preserved exactly. Processing-version changes are an additional source of
nonstationarity; this PoC does not claim that all annual MODIS files have been
reprocessed into one identical collection. Sensor harmonization evaluation must
be interpreted with that limitation.

The Collection 2 VIIRS user guide reports a type-attribution bug affecting old
monthly product versions 1 and 2; version 3 was reprocessed following the May
2025 correction. The FIRMS CSV `version` field alone is not sufficient to infer
the underlying monthly product revision: for example, `2` denotes Collection 2
in the annual VIIRS CSV. Archive update timestamps and CSV version values are
preserved in provenance; this PoC does not independently validate every inferred
type label against the original monthly products.

### Interpretation and temporal coverage

An active-fire point identifies the center of a pixel containing a detected
thermal anomaly at satellite overpass time. It is not one independently counted
fire, its pixel dimensions do not equal burned area, and repeated points do not
measure accumulated burned hectares. Detection sensitivity, footprint size,
view angle, overpass schedule, satellite constellation, cloud/smoke cover, and
algorithm processing can all change the observed count.

The CSV contains positive detections, not the complete clear/cloudy/missing
observation mask. Zero counts therefore mean **no retained detections**, not
proof that no fire occurred or that observations were complete. Calibration
using these CSVs cannot correct every missing observation.

VIIRS Suomi-NPP begins on 20 January 2012; January 2012 is partial. MODIS starts
with Terra, with Aqua observations beginning in July 2002. Annual archive
acquisition is checked against the official manifest, but this does not prove
every satellite overpass is present. Exact first/last **detections** per file
are recorded; they are not treated as sensor exposure dates.

NASA references:

- [FIRMS field definitions and archive readme](https://firms.modaps.eosdis.nasa.gov/data/country/AttributesReadme.txt)
- [MODIS Collection 6 / 6.1 Active Fire User Guide](https://www.earthdata.nasa.gov/s3fs-public/2023-09/MODIS_C6_C6.1_Fire_User_Guide_1.0.pdf)
- [VIIRS Collection 2 375 m Active Fire User Guide v1.2](https://www.earthdata.nasa.gov/s3fs-public/2025-06/VIIRS_C2_AF-375m_User_Guide_1.2.pdf)
- [NASA: caveats when using FIRMS active-fire data](https://forum.earthdata.nasa.gov/viewtopic.php?t=5188)
- [NASA: what a detection means on the ground](https://forum.earthdata.nasa.gov/viewtopic.php?t=5155)

Suggested acknowledgement: “MODIS and VIIRS 375 m active
fire/hotspot data were acquired using FIRMS, part of NASA's Land, Atmosphere
Near real-time Capability for EOS (LANCE), with funding provided by NASA
Headquarters.” Link to [NASA FIRMS data-use guidance](https://www.earthdata.nasa.gov/data/tools/firms).

## CAL FIRE historical fire perimeters

- **Source:** [California Fire Perimeters (all), CAL FIRE FRAP](https://data.ca.gov/@cal-fire/california-fire-perimeters-all).
- **Service:** [California Historic Fire Perimeters, layer 0](https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/California_Historic_Fire_Perimeters/FeatureServer/0).
- **Snapshot version:** firep25_1, including the 2025 season, according to the
  official catalogue available in November 2026.
- **Query:** `STATE = 'CA' AND YEAR_ >= 2001 AND YEAR_ <= 2025`.
- **Statistical unit:** a positive-area perimeter record with unique GlobalID.
  Records retain IRWINID, complex ID/name, cause, management objective, agency,
  alarm and containment dates when provided.
- **Area:** source `GIS_ACRES × 0.40468564224` hectares. This remains the full
  reported event perimeter area, not an area clipped to an arbitrary AOI.
- **Geometry:** WGS84 GeoJSON requested with a 0.0005 degree generalization
  tolerance to keep display files small. Statistical areas are read from the
  original source attribute and are not recomputed from generalized polygons.
- **AOI convention:** centroids are stored for selecting whole perimeter records
  by location. This convention must be visible wherever AOI perimeter statistics
  are shown; a centroid selection can omit a boundary-crossing event.

CAL FIRE explicitly documents incompleteness, duplicates, missing perimeters,
and generalized geometry. Current reporting criteria differ by vegetation:
CAL FIRE and contract counties report fires at least 10 acres in timber, 50
acres in brush, or 300 acres in grass, and/or fires affecting at least three
structures or causing a fatality. Cooperating agencies report perimeters at
least 10 acres. Historical criteria can differ. A tail threshold reduces some
small-event selection effects but does not establish perfect completeness.

Complex and child perimeters can coexist. Unique GlobalID does not guarantee
independent, non-overlapping fire events. Strong power-law conclusions require
complex/duplicate sensitivity checks, model comparison, and explicit sample-size
and threshold reporting. A perimeter can include unburned islands, so even this
area is not an exact pixelwise burn scar.

The prepared snapshot contains **8,699 unique-GlobalID positive-area perimeter
records**. An independent count-only service query returned the same 8,699
matching source features, confirming the pagination count. Eight nonempty IRWINID
groups have multiple records, sometimes with different fire names; these cannot
automatically be assumed to be duplicate fires. There are 604 records with
complex names, of which 583 also have complex IDs.

CAL FIRE credits cooperating federal, state, and local agencies; preserve that
attribution. The catalogue lists Creative Commons Attribution and no
restrictions on public use.

## California boundary

[U.S. Census Bureau Census 2020 State/County service](https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/State_County/MapServer/0),
query `STATE='06'`, output EPSG:4326. The acquisition mask uses a 0.00001 degree
service generalization tolerance; `california.geojson` is simplified to 0.002
degrees only for display. The mask includes the state polygon's coastal waters;
the NASA annual country-source filter also applies.

## Reproduction

Run `.venv/bin/python scripts/fetch_data.py --workers 3` from the checkout.
Public archive downloads require network access but no API credential. NASA
FIRMS and Earthdata keys in the root `.env` are unnecessary for this historical
snapshot and are not read by the downloader. Optional future near-real-time
refresh must use server-side environment variables and must not log keyed URLs.

Cached raw sources are reused; remove only the particular cached source if a
fresh source release is intentionally required, then regenerate provenance and
all derived analyses. Keep source and derived snapshot versions together.
