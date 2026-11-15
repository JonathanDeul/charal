#!/usr/bin/env python3
"""Prepare daily support and a separately fitted, smooth seasonal calibration."""
from pathlib import Path
from datetime import date
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from shapely.geometry import box, shape
from backend.anomalies import EPOCH, END, calendar_axis, fit_seasonal_ratios


def main():
    folder = ROOT / 'data' / 'processed'
    boundary = json.loads((ROOT / 'data/raw/california_census2020.geojson').read_text())
    from shapely.ops import unary_union
    region = unary_union([shape(f['geometry']) for f in boundary['features']]) if boundary['type'] == 'FeatureCollection' else shape(boundary.get('geometry', boundary))
    cells = [(y, x) for y in range(64, 85) for x in range(-250, -227)
             if region.intersects(box(x/2, y/2, (x+1)/2, (y+1)/2))]
    lookup = {cell: i for i, cell in enumerate(cells)}
    n = (END - EPOCH).days + 1
    counts = [np.zeros((n, len(cells)), dtype=np.int32) for _ in range(2)]
    with np.load(folder / 'observations.npz', allow_pickle=False) as obs:
        keys = zip(np.floor(obs['latitude'].astype(float) * 2).astype(int), np.floor(obs['longitude'].astype(float) * 2).astype(int))
        indices = np.array([lookup.get(key, -1) for key in keys])
        if (indices < 0).any():
            raise ValueError('A retained detection falls outside the fixed California grid')
        for sensor in range(2):
            keep = obs['sensor'] == sensor
            np.add.at(counts[sensor], (obs['day'][keep], indices[keep]), 1)
    coverage = json.loads((folder / 'coverage.json').read_text())
    modis_valid, viirs_valid = np.ones(n, dtype=bool), np.ones(n, dtype=bool)
    for target, satellites in [(modis_valid, ['Terra', 'Aqua']), (viirs_valid, ['Suomi NPP'])]:
        for satellite in satellites:
            for text in coverage['flagged_dates_by_satellite'][satellite]:
                day = (date.fromisoformat(text) - EPOCH).days
                if 0 <= day < n:
                    target[day] = False
    viirs_valid[:(date(2012, 1, 20) - EPOCH).days] = False
    years, season = calendar_axis(n)
    ratios = fit_seasonal_ratios(*counts, modis_valid & viirs_valid, years, season)
    ratios_by_year = np.array([fit_seasonal_ratios(*counts, modis_valid & viirs_valid, years, season, exclude_year=y)
                               if 2013 <= y <= 2020 else ratios for y in range(2001, 2026)])
    ratios_by_pair = np.array([fit_seasonal_ratios(*counts, modis_valid & viirs_valid, years, season, exclude_year=[y,y+1])
                               if 2012 <= y <= 2020 else ratios for y in range(2001, 2025)])
    np.savez_compressed(folder / 'activity_daily.npz', modis=counts[0], viirs=counts[1],
                        modis_valid=modis_valid, viirs_valid=viirs_valid, ratios=ratios, ratios_by_year=ratios_by_year, ratios_by_pair=ratios_by_pair,
                        years=years.astype(np.int16), season=season.astype(np.int16),
                        latitude=np.array([(y+.5)/2 for y, x in cells]),
                        longitude=np.array([(x+.5)/2 for y, x in cells]))
    meta = {'schema_version': 1, 'grid_degrees': .5, 'days': n, 'cells': len(cells),
            'train_years': list(range(2013, 2021)), 'calibration': 'Raised-cosine ±30 calendar-day ratio of pooled training sensor totals; applied to actual daily MODIS counts.',
            'reference_switch': '2012-02-01', 'calibration_exclusion': 'All calendar years covered by the target measurement are also left out of the sensor-ratio fit.',
            'ratio_min': float(ratios.min()), 'ratio_max': float(ratios.max()),
            'input_sha256': {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in ['observations.npz', 'coverage.json']},
            'boundary_sha256': hashlib.sha256((ROOT / 'data/raw/california_census2020.geojson').read_bytes()).hexdigest(),
            'limitations': ['Exploratory daily calibration; monthly model validation does not validate these windows.',
                           'Early Terra-only sampling, orbit drift, clouds and unlisted local gaps remain.',
                           'Ranks describe activity in a fixed 2001–2025 historical reference, not present-day climate or a calibrated tail probability.']}
    (folder / 'activity_metadata.json').write_text(json.dumps(meta, indent=2) + '\n')
    print(json.dumps(meta, indent=2))


if __name__ == '__main__':
    main()
