#!/usr/bin/env python3
"""Geolocate one genuine 375m SNPP fire-mask swath for the MODIS pilot date."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlparse

from dotenv import dotenv_values
import h5py
import numpy as np
import pandas as pd
import requests
from shapely import intersects_xy
from shapely.geometry import shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/research/harmonization_v2"
CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
SWATH = "A2020233.1936"


def main():
    cache = OUT / "masks"
    cache.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.verify = "/etc/ssl/cert.pem"
    token = dotenv_values(ROOT / ".env").get("EARTHDATA_KEY", "")
    manifest = {"source": CMR, "swath": SWATH, "files": [], "status": "pending",
        "limitations": ["One six-minute daytime swath, not full-day or full-period reference exposure.",
            "Bowtie, glint, cloudy and unprocessed classes are retained separately.",
            "375m swath and 1km daily maximum MODIS composites have different spatial/temporal supports.",
            "Masks are not fitted as full-period predictors; historical model remains hotspot-only."]}
    paths = {}
    for product, version in [("VNP14IMG", "002"), ("VNP03IMG", "2")]:
        r = session.get(CMR, params={"short_name": product, "version": version,
            "temporal": "2020-08-20T19:36:00Z,2020-08-20T19:41:59Z", "page_size": 30}, timeout=60)
        r.raise_for_status()
        links = [link["href"] for entry in r.json()["feed"]["entry"] for link in entry["links"]
                 if link.get("rel", "").endswith("/data#") and SWATH in link.get("href", "") and link["href"].endswith(".nc")]
        if len(links) != 1:
            raise ValueError(f"Expected exactly one matching geolocation/fire granule for {product}")
        url = links[0]
        if urlparse(url).hostname not in {"data.lpdaac.earthdatacloud.nasa.gov", "data.laadsdaac.earthdatacloud.nasa.gov"}:
            raise ValueError("Unexpected download host")
        path = cache / url.rsplit("/", 1)[1]
        info = {"product": product, "url": url, "granule": path.name}
        if not path.exists():
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            with session.get(url, headers=headers, stream=True, timeout=120) as response:
                if response.status_code in (401, 403) or urlparse(response.url).hostname == "urs.earthdata.nasa.gov":
                    manifest.update(status="blocked_authentication")
                    info["status"] = "earthdata_authentication_required_or_rejected"
                    manifest["files"].append(info)
                    (OUT / "viirs_mask_pilot.json").write_text(json.dumps(manifest, indent=2))
                    print("VIIRS pilot requires a valid Earthdata token for", product, flush=True)
                    return
                response.raise_for_status()
                temporary = path.with_suffix(".tmp")
                with temporary.open("wb") as f:
                    for chunk in response.iter_content(1 << 20):
                        f.write(chunk)
                with temporary.open("rb") as f:
                    if f.read(8) != b"\x89HDF\r\n\x1a\n":
                        temporary.unlink()
                        raise ValueError("NASA download was not HDF5/NetCDF4")
                temporary.replace(path)
        info.update(status="downloaded", bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        manifest["files"].append(info)
        paths[product] = path
        print("Acquired", product, path.stat().st_size, "bytes", flush=True)
    geometry = json.loads((ROOT / "data/raw/california_census2020.geojson").read_text())
    ca = unary_union([shape(f["geometry"]) for f in geometry["features"]])
    pieces = []
    with h5py.File(paths["VNP14IMG"]) as fire, h5py.File(paths["VNP03IMG"]) as geo:
        mask = fire["fire mask"]
        lat = geo["geolocation_data/latitude"]
        lon = geo["geolocation_data/longitude"]
        if mask.shape != lat.shape or mask.shape != lon.shape:
            raise ValueError("Fire mask and geolocation shapes differ")
        manifest["swath_shape"] = list(mask.shape)
        for start in range(0, mask.shape[0], 256):
            latitude, longitude = lat[start:start+256], lon[start:start+256]
            selected = intersects_xy(ca, longitude, latitude)
            values = mask[start:start+256][selected]
            if not len(values):
                continue
            block = pd.DataFrame({"gy": np.floor(latitude[selected]*2).astype(int),
                "gx": np.floor(longitude[selected]*2).astype(int), "mask_class": values.astype(int)})
            pieces.append(block.groupby(["gy", "gx", "mask_class"]).size().rename("pixels").reset_index())
    if not pieces:
        raise ValueError("Selected VIIRS swath has no California pixels")
    data = pd.concat(pieces).groupby(["gy", "gx", "mask_class"], as_index=False).pixels.sum()
    data["date"] = "2020-08-20"
    data["time_utc"] = "19:36"
    data.to_csv(OUT / "viirs_mask_pilot_cells.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    manifest["mask_classes"] = {"0": "not processed", "1": "bowtie", "2": "glint", "3": "water", "4": "cloud",
        "5": "clear land", "6": "unclassified", "7": "low-confidence fire", "8": "nominal-confidence fire", "9": "high-confidence fire"}
    manifest["pixels_by_class"] = {str(k): int(v) for k, v in data.groupby("mask_class").pixels.sum().items()}
    manifest["status"] = "acquired_and_geolocated"
    manifest["cells"] = len(data[["gy", "gx"]].drop_duplicates())
    (OUT / "viirs_mask_pilot.json").write_text(json.dumps(manifest, indent=2))
    print("VIIRS pilot complete:", manifest["cells"], "California cells", flush=True)


if __name__ == "__main__":
    main()
