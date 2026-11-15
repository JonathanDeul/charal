#!/usr/bin/env python3
"""Bounded MODIS fire-mask pilot, using NASA CMR and a server-side EDL token.

No credential, keyed URL or response body is printed or saved in provenance.
This samples two eight-day periods; it does NOT establish full-period exposure.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

import numpy as np
import pandas as pd
from dotenv import dotenv_values
from pyhdf.SD import SD, SDC
from pyproj import Transformer
import requests
from shapely import intersects_xy
from shapely.geometry import shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/research/harmonization_v2"
CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
PERIODS = ["2018-07-20", "2020-08-20"]
TILES = {"h08v04", "h08v05", "h09v04", "h09v05"}
HOSTS = {"data.lpdaac.earthdatacloud.nasa.gov", "urs.earthdata.nasa.gov"}


def aggregate_mask(path, grid, ca):
    """Count mask classes for pixel centers in CA and the fixed analysis cells.

    MOD14A1 daily mask: 0 not processed, 1 not processed obsolete, 2 not
    processed other, 3 non-fire water, 4 cloud, 5 non-fire land, 6 unknown,
    7/8/9 fire. Daily maximum composites are not overpass-level exposure.
    """
    h, v = map(int, re.search(r"h(\d{2})v(\d{2})", path.name).groups())
    sd = SD(str(path), SDC.READ)
    sds = sd.select("FireMask")
    data = sds[:]
    sds.endaccess()
    sd.end()
    if data.ndim != 3 or data.shape[0] != 8:
        raise ValueError("Expected eight daily MOD14A1 fire masks")
    tile_size = 1111950.5196666666
    n_y, n_x = data.shape[1:]
    xs = -20015109.354 + (h + (np.arange(n_x)+.5)/n_x)*tile_size
    ys = 10007554.677 - (v + (np.arange(n_y)+.5)/n_y)*tile_size
    xx, yy = np.meshgrid(xs, ys)
    transformer = Transformer.from_crs("+proj=sinu +R=6371007.181 +nadgrids=@null +wktext", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(xx, yy)
    selected = intersects_xy(ca, lon, lat)
    gx, gy = np.floor(lon[selected]*2).astype(int), np.floor(lat[selected]*2).astype(int)
    lookup = {(int(r.gy), int(r.gx)): i for i, r in grid.iterrows()}
    ids = np.array([lookup.get((y, x), -1) for y, x in zip(gy, gx)], dtype=np.int64)
    valid = ids >= 0
    ids = ids[valid]
    date_match = re.search(r"\.A(\d{7})\.", path.name)
    start = datetime.strptime(date_match[1], "%Y%j")
    rows = []
    for day, mask in enumerate(data):
        values = mask[selected][valid]
        total = np.bincount(ids, minlength=len(grid))
        # Count named classes; retain the denominator and unobserved classes.
        classes = {name: np.bincount(ids[np.isin(values, codes)], minlength=len(grid)) for name, codes in {
            "cloud_pixels": [4], "clear_land_pixels": [5, 7, 8, 9], "fire_pixels": [7, 8, 9],
            "water_pixels": [3], "unprocessed_pixels": [0, 1, 2], "unknown_pixels": [6]}.items()}
        for i in np.flatnonzero(total):
            rows.append({"date": (start+timedelta(days=day)).strftime("%Y-%m-%d"),
                "gy": int(grid.iloc[i].gy), "gx": int(grid.iloc[i].gx), "pixel_centers": int(total[i]),
                **{k: int(c[i]) for k, c in classes.items()}})
    return pd.DataFrame(rows, columns=["date", "gy", "gx", "pixel_centers", "cloud_pixels", "clear_land_pixels",
        "fire_pixels", "water_pixels", "unprocessed_pixels", "unknown_pixels"])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / "masks"
    cache.mkdir(exist_ok=True)
    token = dotenv_values(ROOT / ".env").get("EARTHDATA_KEY", "")
    session = requests.Session()
    session.verify = "/etc/ssl/cert.pem"
    session.headers["User-Agent"] = "Charal-harmonization-research/2"
    grid = pd.read_csv(OUT / "grid.csv")
    grid = grid[grid.state.eq("CA")].reset_index(drop=True)
    geometry = json.loads((ROOT / "data/raw/california_census2020.geojson").read_text())
    ca = unary_union([shape(f["geometry"]) for f in geometry["features"]])
    manifest = {"source": CMR, "period_queries": PERIODS, "products": ["MOD14A1.061", "MYD14A1.061"],
        "tiles": sorted(TILES), "files": [], "status": "pending", "generated_at": datetime.now(timezone.utc).isoformat(),
        "limitations": ["Pilot only; not used as full-period model predictors.",
            "Daily MOD14A1 maximum fire-mask composites do not preserve each overpass observation.",
            "Cloud/smoke and unknown classes are not interchangeable; mask cannot reconstruct every missed fire.",
            "MODIS masks do not measure SNPP 375m reference exposure; matched VIIRS L2 masks remain necessary before exposure-aware training."]}
    aggregates = []
    authentication_failed = False
    for product in ("MOD14A1", "MYD14A1"):
        for period in PERIODS:
            r = session.get(CMR, params={"short_name": product, "version": "061", "temporal": period+"T00:00:00Z,"+period+"T23:59:59Z",
                "bounding_box": "-125,32,-114,42.5", "page_size": 200}, timeout=60)
            r.raise_for_status()
            entries = r.json()["feed"]["entry"]
            for entry in entries:
                title = entry.get("producer_granule_id", entry["title"])
                if not any(tile in title for tile in TILES):
                    continue
                links = [x["href"] for x in entry["links"] if x.get("rel", "").endswith("/data#") and x.get("href", "").endswith(".hdf")]
                if not links:
                    continue
                url = links[0]
                if urlparse(url).hostname not in HOSTS:
                    raise ValueError("Unexpected NASA download host")
                path = cache / url.rsplit("/", 1)[1]
                info = {"product": product, "granule": path.name, "url": url}
                if not path.exists() and not authentication_failed:
                    headers = {"Authorization": f"Bearer {token}"} if token else {}
                    # Requests strips authentication on cross-host redirects.
                    response = session.get(url, headers=headers, timeout=90, allow_redirects=True)
                    if response.status_code in (401, 403) or "urs.earthdata.nasa.gov" in response.url or response.content[:4] != b"\x0e\x03\x13\x01":
                        authentication_failed = True
                        info["status"] = "earthdata_authentication_required_or_rejected"
                        info["http_status"] = response.status_code
                    else:
                        response.raise_for_status()
                        path.write_bytes(response.content)
                if path.exists():
                    info.update({"status": "downloaded", "bytes": path.stat().st_size,
                                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
                    block = aggregate_mask(path, grid, ca)
                    block["product"] = product
                    aggregates.append(block)
                    print(product, path.name, "mask cells", len(block), flush=True)
                else:
                    info.setdefault("status", "not_downloaded_after_authentication_failure")
                manifest["files"].append(info)
    if aggregates:
        data = pd.concat(aggregates, ignore_index=True)
        data = data.groupby(["product", "date", "gy", "gx"], as_index=False).sum()
        data.to_csv(OUT / "mask_pilot_cells.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
        manifest["cell_days"] = len(data)
    acquired = sum(f["status"] == "downloaded" for f in manifest["files"])
    manifest["status"] = "acquired" if acquired == len(manifest["files"]) and acquired else "partial" if acquired else "blocked_authentication" if authentication_failed else "no_matching_granules"
    (OUT / "mask_pilot.json").write_text(json.dumps(manifest, indent=2))
    print("Mask pilot:", manifest["status"], acquired, "of", len(manifest["files"]), flush=True)


if __name__ == "__main__":
    main()
