#!/usr/bin/env python3
"""Reproduce the California 2001–2025 public-data snapshot.

No credentials are needed for these public historical archives. API keys in the
workspace are intentionally not read, logged, or embedded in provenance.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import ssl
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd
from shapely.geometry import mapping, shape
from shapely import intersects_xy

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
OUT = ROOT / "data/processed"
FIRMS = "https://firms.modaps.eosdis.nasa.gov"
MANIFEST = FIRMS + "/data/country/yearly_summary_files.txt"
PERIMETERS = "https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/California_Historic_Fire_Perimeters/FeatureServer/0"
BOUNDARY = "https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/State_County/MapServer/0"
SSL = ssl.create_default_context(cafile="/etc/ssl/cert.pem" if Path("/etc/ssl/cert.pem").exists() else None)
ACRE_HA = 0.40468564224


def request(url: str, params: dict | None = None, timeout: int = 180) -> bytes:
    if params:
        url += "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "California-SpaceApps-research-PoC/1.0"})
            with urllib.request.urlopen(req, context=SSL, timeout=timeout) as response:
                return response.read()
        except Exception as exc:
            if attempt == 3:
                # URLs are public, but logging their absence also keeps this safe
                # if a future API-based implementation uses credentialed URLs.
                raise RuntimeError(f"Public source request failed: {type(exc).__name__}") from None
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def get_json(url: str, params: dict) -> dict:
    result = json.loads(request(url, params))
    if "error" in result:
        raise RuntimeError("Public source returned error: " + str(result["error"].get("message", "unknown")))
    return result


def california_boundary() -> tuple[dict, object]:
    path = RAW / "california_census2020.geojson"
    params = {"where": "STATE='06'", "outFields": "NAME,STATE,GEOID", "outSR": 4326,
              "f": "geojson", "maxAllowableOffset": "0.00001", "returnGeometry": "true"}
    if not path.exists():
        path.write_text(json.dumps(get_json(BOUNDARY + "/query", params), separators=(",", ":")))
    geo = json.loads(path.read_text())
    if len(geo.get("features", [])) != 1:
        raise RuntimeError("California boundary must contain exactly one feature")
    geom = shape(geo["features"][0]["geometry"])
    if not geom.is_valid:
        geom = geom.buffer(0)
    # Preserve accurate geometry for masking; lighter geometry for map rendering.
    display = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "California", "source": "U.S. Census Bureau, Census 2020"}, "geometry": mapping(geom.simplify(0.002, preserve_topology=True))}]}
    (OUT / "california.geojson").write_text(json.dumps(display, separators=(",", ":")))
    return geo, geom


def fetch_firms_one(item: tuple[str, int, dict]) -> dict:
    sensor, year, info = item
    filename = f"{sensor}_{year}_United_States.csv"
    url = f"{FIRMS}/data/country/{sensor}/{year}/{filename}"
    path = RAW / (filename + ".gz")
    if not path.exists():
        data = request(url)
        # Validate expected CSV before preserving. NASA may return HTML errors.
        if not data.startswith(b"latitude,longitude,"):
            raise RuntimeError(f"Invalid NASA CSV for {sensor} {year}")
        if len(data) != int(info["size"]):
            raise RuntimeError(f"NASA size mismatch for {sensor} {year}")
        tmp = path.with_suffix(".tmp")
        with gzip.open(tmp, "wb", compresslevel=3) as f:
            f.write(data)
        tmp.replace(path)
    else:
        with gzip.open(path, "rb") as f:
            data = f.read()
    # Read bbox subset immediately, reducing the memory needed for final concat.
    frame = pd.read_csv(io.BytesIO(data), dtype={"acq_time": str, "confidence": str, "version": str, "satellite": str})
    frame = frame.loc[frame.latitude.between(32.5, 42.1) & frame.longitude.between(-124.5, -114.1)].copy()
    frame["sensor"] = "MODIS" if sensor == "modis" else "VIIRS"
    frame["year"] = year
    # Per-year small candidates allow a robust, resumable final processing stage.
    candidate = RAW / f"candidate_{sensor}_{year}.csv"
    frame.to_csv(candidate, index=False)
    metadata = {"sensor": "MODIS" if sensor == "modis" else "VIIRS", "satellite_source": sensor,
                "year": year, "url": url, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                "archive_updated_utc": info["updated"], "bbox_candidate_rows": len(frame),
                "candidate_file": str(candidate.relative_to(ROOT))}
    print(f"NASA {sensor} {year}: {len(frame):,} bbox candidates", flush=True)
    return metadata


def nasa_hotspots(boundary, workers: int) -> dict:
    manifest_text = request(MANIFEST).decode()
    (RAW / "yearly_summary_files.txt").write_text(manifest_text)
    manifest = {r["filename"]: r for r in csv.DictReader(io.StringIO(manifest_text))}
    requested = [("modis", year) for year in range(2001, 2026)] + [("viirs-snpp", year) for year in range(2012, 2026)]
    jobs = []
    for sensor, year in requested:
        filename = f"{sensor}_{year}_United_States.csv"
        if filename not in manifest:
            raise RuntimeError(f"Missing NASA archive file: {sensor} {year}")
        jobs.append((sensor, year, manifest[filename]))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        sources = list(pool.map(fetch_firms_one, jobs))
    frames = [pd.read_csv(ROOT / source["candidate_file"], dtype={"acq_time": str, "confidence": str, "version": str, "satellite": str}) for source in sources]
    frame = pd.concat(frames, ignore_index=True)
    count_bbox = len(frame)
    # Census state polygon includes offshore state waters. All candidates are from
    # NASA's United States country archive, then polygon-clipped here.
    frame = frame.loc[intersects_xy(boundary, frame.longitude.to_numpy(), frame.latitude.to_numpy())].copy()
    before_dedup = len(frame)
    frame = frame.drop_duplicates(subset=["latitude", "longitude", "acq_date", "acq_time", "sensor", "satellite", "frp"])
    frame["month"] = pd.to_datetime(frame.acq_date).dt.month
    frame["acq_time"] = frame.acq_time.str.zfill(4)
    # Common geometry / temporal aggregation occurs downstream, preserving raw
    # per-detection information in this prepared snapshot.
    fields = ["latitude", "longitude", "acq_date", "acq_time", "sensor", "satellite", "frp", "confidence", "daynight", "year", "month", "version", "type", "scan", "track", "brightness", "bright_t31", "bright_ti4", "bright_ti5"]
    for col in fields:
        if col not in frame:
            frame[col] = np.nan
    frame = frame[fields].sort_values(["acq_date", "acq_time", "sensor", "latitude", "longitude"])
    frame.to_csv(OUT / "hotspots.csv", index=False)
    for source in sources:
        block = frame[(frame.sensor == source["sensor"]) & (frame.year == source["year"])]
        source.update({"california_rows": len(block), "first_detection": str(block.acq_date.min()), "last_detection": str(block.acq_date.max()),
                       "product_versions": sorted(block.version.dropna().astype(str).unique().tolist())})
    return {"manifest_url": MANIFEST, "source": "NASA FIRMS standard-processing annual country archives", "sources": sources,
            "requested_files": len(jobs), "acquired_files": len(sources), "requested_years": {"MODIS": [2001, 2025], "VIIRS_SNPP": [2012, 2025]},
            "rows": len(frame), "bbox_rows": count_bbox, "exact_duplicate_rows_removed": before_dedup - len(frame),
            "filter": "United States country archive; bbox [-124.5,32.5,-114.1,42.1]; point intersects Census 2020 California state polygon; all confidence and type values retained",
            "counts_by_sensor": {str(k): int(v) for k, v in frame.groupby("sensor").size().items()},
            "counts_by_sensor_type": [{"sensor": str(sensor), "type": int(kind), "count": int(count)} for (sensor, kind), count in frame.groupby(["sensor", "type"]).size().items()],
            "csv_versions": {str(sensor): sorted(block.version.dropna().astype(str).unique().tolist()) for sensor, block in frame.groupby("sensor")},
            "counts_by_sensor_year": [{"sensor": str(sensor), "year": int(year), "count": int(count)} for (sensor, year), count in frame.groupby(["sensor", "year"]).size().items()],
            "limitations": ["Hotspots are pixel detections, not unique fires or burned area.", "Point CSVs do not encode cloud/clear-sky exposure or all missing observations.", "VIIRS SNPP begins 20 January 2012; January 2012 is partial.", "MODIS Terra-only early record precedes Aqua operational observations in July 2002.", "Different spatial sensitivity, acquisition times, and satellite availability require calibration.", "The public MODIS annual archive mixes CSV version values (6.2 before 2018; 6.03 in 2018–2022; 61.03 in 2023–2025); processing changes may influence comparisons.", "The VIIRS CSV version value 2 is a collection marker and does not by itself establish the monthly algorithm revision.", "All thermal-anomaly types are retained in the prepared CSV; downstream vegetation/quality filters must be documented."]}


def fire_perimeters() -> dict:
    features = []
    offset = 0
    where = "YEAR_ >= 2001 AND YEAR_ <= 2025 AND STATE = 'CA'"
    expected_count = get_json(PERIMETERS + "/query", {"where": where, "returnCountOnly": "true", "f": "json"})["count"]
    while True:
        path = RAW / f"frap_page_{offset}.geojson"
        if not path.exists():
            params = {"where": where, "outFields": "*", "outSR": 4326, "f": "geojson", "returnGeometry": "true",
                      "resultOffset": offset, "resultRecordCount": 1000, "orderByFields": "OBJECTID", "maxAllowableOffset": 0.0005}
            path.write_text(json.dumps(get_json(PERIMETERS + "/query", params), separators=(",", ":")))
        obj = json.loads(path.read_text())
        batch = obj.get("features", [])
        features.extend(batch)
        print(f"CAL FIRE: {len(features):,} perimeter features", flush=True)
        if len(batch) < 1000:
            break
        offset += 1000
    if len(features) != expected_count:
        raise RuntimeError("CAL FIRE pagination count does not match source count query")
    records = []
    invalid = 0
    for feat in features:
        p = feat["properties"]
        acres = p.get("GIS_ACRES")
        if not acres or acres <= 0 or not feat.get("geometry"):
            invalid += 1
            continue
        geom = shape(feat["geometry"])
        if not geom.is_valid:
            geom = geom.buffer(0)
        if geom.is_empty:
            invalid += 1
            continue
        centroid = geom.centroid
        records.append({"id": str(p.get("GlobalID") or p["OBJECTID"]), "object_id": p["OBJECTID"], "name": p.get("FIRE_NAME") or "Unnamed fire",
                        "year": int(p["YEAR_"]), "area_ha": float(acres) * ACRE_HA, "area_acres": float(acres),
                        "latitude": centroid.y, "longitude": centroid.x, "geometry": mapping(geom),
                        "irwin_id": p.get("IRWINID"), "complex_id": p.get("COMPLEX_ID"), "complex_name": p.get("COMPLEX_NAME"),
                        "agency": p.get("AGENCY"), "cause": p.get("CAUSE"), "alarm_date_ms": p.get("ALARM_DATE"),
                        "containment_date_ms": p.get("CONT_DATE"), "objective": p.get("OBJECTIVE")})
    # Do not dissolve complexes: they may include overlapping child records.
    # The statistics operate on perimeter records and explicitly document this.
    seen = set()
    unique = []
    for rec in records:
        if rec["id"] not in seen:
            unique.append(rec)
            seen.add(rec["id"])
    (OUT / "perimeters.json").write_text(json.dumps(unique, separators=(",", ":")))
    counts = pd.Series([r["year"] for r in unique]).value_counts().sort_index()
    return {"source": "CAL FIRE FRAP California Historic Fire Perimeters, firep25_1", "url": PERIMETERS,
            "catalog_url": "https://data.ca.gov/@cal-fire/california-fire-perimeters-all", "where": where, "feature_count": len(unique), "source_query_count": expected_count,
            "invalid_or_nonpositive_records_excluded": invalid, "duplicate_global_ids_removed": len(records) - len(unique),
            "counts_by_year": {str(k): int(v) for k, v in counts.items()},
            "area_measure": "GIS_ACRES × 0.40468564224; full reported perimeter area, not clipped to AOI",
            "geometry": "WGS84 GeoJSON; service generalization maxAllowableOffset 0.0005 degrees for display and centroid selection; statistical areas use original GIS_ACRES",
            "selection": "STATE='CA'; year 2001–2025; positive GIS_ACRES; unique GlobalID. Each record is a reported fire perimeter, not necessarily an independent complex.",
            "limitations": ["The record is incomplete; missing perimeters, duplicated fires, and generalized geometry are documented by CAL FIRE.",
                           "Current reporting criteria: CAL FIRE/contract counties ≥10 acres timber, ≥50 acres brush, ≥300 acres grass, and/or ≥3 impacted structures or ≥1 fatality; cooperating agencies ≥10 acres.",
                           "Historical collection criteria can differ; a common tail threshold does not guarantee complete sampling.",
                           "Complex and child perimeter records can coexist; explicit complex handling or sensitivity analysis is needed before strong inferential claims.",
                           "Full reported perimeter area can include unburned islands and cannot be interpreted as exact burned land area.",
                           "Perimeter centroids are for spatial selection; an AOI selects entire events by centroid, not partial clipped areas."]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--skip-nasa", action="store_true")
    parser.add_argument("--skip-perimeters", action="store_true")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    _, boundary = california_boundary()
    path = ROOT / "data/provenance.json"
    provenance = json.loads(path.read_text()) if path.exists() else {}
    provenance.update({"prepared_at_utc": datetime.now(timezone.utc).isoformat(), "region": "California", "period": [2001, 2025],
                       "boundary": {"url": BOUNDARY, "vintage": "Census 2020", "mask_generalization_degrees": 0.00001, "display_generalization_degrees": 0.002},
                       "credentials_used": False, "synthetic_data": False})
    if not args.skip_perimeters:
        provenance["perimeters"] = fire_perimeters()
        path.write_text(json.dumps(provenance, indent=2))
    if not args.skip_nasa:
        provenance["hotspots"] = nasa_hotspots(boundary, max(1, min(4, args.workers)))
        path.write_text(json.dumps(provenance, indent=2))
    print("Prepared public real-data snapshot and source provenance.", flush=True)


if __name__ == "__main__":
    main()
