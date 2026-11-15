#!/usr/bin/env python3
"""Reprocess cached US FIRMS archives; acquire public Census/EPA geography."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from shapely import intersects_xy
from shapely.geometry import box, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fetch_data import get_json
from backend.science import eligible_hotspots

OUT = ROOT / "data/research/harmonization_v2"
STATES = {"CA": "06", "OR": "41", "WA": "53", "NV": "32", "AZ": "04"}
EPA = "https://gispub.epa.gov/arcgis/rest/services/ORD/USEPA_Ecoregions_Level_III_and_IV/MapServer/11"
CENSUS = "https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/State_County/MapServer/0"
KEYS = ["state", "gy", "gx", "year", "month"]


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def geography():
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "geography.json"
    if path.exists():
        return json.loads(path.read_text())
    boundaries = {}
    for state, fips in STATES.items():
        # Reuse the original acquisition mask for exact California comparability.
        if state == "CA":
            geo = json.loads((ROOT / "data/raw/california_census2020.geojson").read_text())
        else:
            geo = get_json(CENSUS + "/query", {"where": f"STATE='{fips}'", "outFields": "NAME,STATE", "outSR": 4326,
                "f": "geojson", "maxAllowableOffset": 0.00001, "returnGeometry": "true"})
        if len(geo.get("features", [])) != 1:
            raise ValueError(f"Expected one state polygon: {state}")
        boundaries[state] = geo
    meta = get_json(EPA, {"f": "json"})
    print("EPA fields:", [f["name"] for f in meta["fields"]], flush=True)
    eco = get_json(EPA + "/query", {"where": "1=1", "geometry": "-125,31,-109,50", "geometryType": "esriGeometryEnvelope",
        "inSR": 4326, "spatialRel": "esriSpatialRelIntersects", "outFields": "*", "outSR": 4326,
        "f": "geojson", "maxAllowableOffset": 0.002, "returnGeometry": "true", "resultRecordCount": 2000})
    if eco.get("exceededTransferLimit") or not eco.get("features"):
        raise ValueError("EPA query truncated or empty")
    result = {"states": boundaries, "ecoregions": eco, "sources": {"states": CENSUS, "ecoregions": EPA}}
    path.write_text(json.dumps(result, separators=(",", ":")))
    return result


def cell_grid(geo):
    ecogeoms = [(f["properties"], shape(f["geometry"]).buffer(0)) for f in geo["ecoregions"]["features"]]
    rows, boundaries = [], {}
    for state, obj in geo["states"].items():
        region = unary_union([shape(f["geometry"]) for f in obj["features"]]).buffer(0)
        boundaries[state] = region
        w, s, e, n = region.bounds
        for gy in range(int(np.floor(s * 2)), int(np.ceil(n * 2))):
            for gx in range(int(np.floor(w * 2)), int(np.ceil(e * 2))):
                clipped = region.intersection(box(gx / 2, gy / 2, (gx + 1) / 2, (gy + 1) / 2))
                if clipped.is_empty:
                    continue
                # Largest intersection within the state-clipped cell, not a fire-dependent label.
                areas = [(clipped.intersection(g).area, p) for p, g in ecogeoms if clipped.intersects(g)]
                props = max(areas, key=lambda t: t[0])[1] if areas else {}
                code = str(props.get("US_L3CODE", props.get("NA_L3CODE", "unknown")))
                rows.append({"state": state, "gy": gy, "gx": gx, "latitude": (gy + .5) / 2,
                    "longitude": (gx + .5) / 2, "ecoregion": code})
    return pd.DataFrame(rows), boundaries


def summarize(frame):
    modis = frame[frame.sensor.eq("MODIS")].copy()
    modis["terra"] = modis.satellite.str.upper().isin(["TERRA", "T"]).astype(float)
    modis["aqua"] = modis.satellite.str.upper().isin(["AQUA", "A"]).astype(float)
    if not (modis.terra + modis.aqua).eq(1).all():
        raise ValueError("Unknown MODIS platform")
    modis["day"] = modis.daynight.eq("D").astype(float)
    hour = pd.to_numeric(modis.acq_time.str[:2]) + pd.to_numeric(modis.acq_time.str[2:]) / 60
    modis["hour_sin"] = np.sin(hour * 2 * np.pi / 24)
    modis["hour_cos"] = np.cos(hour * 2 * np.pi / 24)
    modis["footprint"] = modis.scan * modis.track
    modis["acquisition"] = modis.acq_date + "_" + modis.acq_time + "_" + modis.satellite
    grouped = modis.groupby(KEYS)
    m = grouped.agg(modis_count=("frp", "size"), frp_sum=("frp", "sum"), frp_mean=("frp", "mean"),
        frp_max=("frp", "max"), frp_std=("frp", "std"), day_fraction=("day", "mean"),
        terra_count=("terra", "sum"), aqua_count=("aqua", "sum"), scan_mean=("scan", "mean"),
        track_mean=("track", "mean"), footprint_mean=("footprint", "mean"),
        hour_sin=("hour_sin", "mean"), hour_cos=("hour_cos", "mean"),
        detection_days=("acq_date", "nunique"), detection_acquisitions=("acquisition", "nunique"))
    v = frame[frame.sensor.eq("VIIRS")]
    if not v.satellite.str.upper().isin(["N", "NPP", "SNPP", "SUOMI-NPP", "S-NPP"]).all():
        raise ValueError("Reference must be SNPP only")
    return m.join(v.groupby(KEYS).size().rename("viirs_count"), how="outer").reset_index()


def main():
    geo = geography()
    grid, boundaries = cell_grid(geo)
    grid.to_csv(OUT / "grid.csv", index=False)
    west = unary_union(list(boundaries.values()))
    bounds = west.bounds
    sources, aggregates, audits = [], [], []
    for sensor, years in [("modis", range(2001, 2026)), ("viirs-snpp", range(2012, 2026))]:
        for year in years:
            path = ROOT / f"data/raw/{sensor}_{year}_United_States.csv.gz"
            blocks = []
            for block in pd.read_csv(path, dtype={"acq_time": str, "confidence": str, "version": str, "satellite": str}, chunksize=200_000):
                block = block[block.longitude.between(bounds[0], bounds[2]) & block.latitude.between(bounds[1], bounds[3])].copy()
                block["sensor"] = "MODIS" if sensor == "modis" else "VIIRS"
                block, audit = eligible_hotspots(block)
                block["year"] = year
                block["month"] = pd.to_datetime(block.acq_date).dt.month
                block["acq_time"] = block.acq_time.str.zfill(4)
                for state, boundary in boundaries.items():
                    subset = block[intersects_xy(boundary, block.longitude.to_numpy(), block.latitude.to_numpy())].copy()
                    if len(subset):
                        subset["state"] = state
                        blocks.append(subset)
            f = pd.concat(blocks, ignore_index=True)
            f = f.drop_duplicates(["state", "latitude", "longitude", "acq_date", "acq_time", "sensor", "satellite", "frp"])
            f["gy"] = np.floor(f.latitude * 2).astype(int)
            f["gx"] = np.floor(f.longitude * 2).astype(int)
            aggregates.append(summarize(f))
            audits.extend({"sensor": sensor, "year": year, "state": state, "retained": int(n)} for state, n in f.groupby("state").size().items())
            sources.append({"path": str(path.relative_to(ROOT)), "sha256": digest(path)})
            print(sensor, year, len(f), flush=True)
    times = pd.MultiIndex.from_product([range(2001, 2026), range(1, 13)], names=["year", "month"]).to_frame(index=False)
    cells = grid.merge(times, how="cross").merge(pd.concat(aggregates, ignore_index=True).groupby(KEYS).sum(min_count=1).reset_index(), on=KEYS, how="left")
    measurements = [c for c in cells if c not in [*KEYS, "ecoregion", "latitude", "longitude"]]
    cells[measurements] = cells[measurements].fillna(0)
    cells.loc[(cells.year < 2012) | ((cells.year == 2012) & (cells.month == 1)), "viirs_count"] = np.nan
    cells["date"] = pd.to_datetime(dict(year=cells.year, month=cells.month, day=1)).dt.strftime("%Y-%m-%d")
    coverage = json.loads((ROOT / "data/processed/coverage.json").read_text())
    complete = {r["date"]: r["modis_missing_day_count"] == 0 and r["viirs_missing_day_count"] == 0 for r in coverage["monthly"]}
    cells["pair_complete"] = cells.date.str[:7].map(complete)
    if cells.pair_complete.isna().any():
        raise ValueError("Missing outage metadata")
    for state in STATES:
        for sensor in ("modis_count", "viirs_count"):
            start = 2001 if sensor == "modis_count" else 2012
            totals = cells[(cells.state == state) & (cells.year >= start)].groupby("year")[sensor].sum()
            if len(totals) != 2026-start or not totals.gt(0).all():
                raise ValueError(f"Missing whole sensor-year: {state} {sensor}")
    cells.to_csv(OUT / "cells.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    manifest = {"sources": sources, "counts": audits, "geography_sha256": digest(OUT / "geography.json"),
        "cells_sha256": digest(OUT / "cells.csv.gz"), "coverage_sha256": digest(ROOT / "data/processed/coverage.json"),
        "grid_rows": len(grid), "cell_months": len(cells), "ecoregion_assignment": "Largest EPA Level III polygon intersection within each state-clipped cell, planar degree-area proxy.",
        "limitations": ["Detection days/acquisitions are not observed clear-sky exposure.", "Detection-pixel geometry is not geometry of all observations.", "No land-cover time series acquired; static 2011 EPA regions are ecological proxies."]}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print("Saved", OUT, flush=True)


if __name__ == "__main__":
    main()
