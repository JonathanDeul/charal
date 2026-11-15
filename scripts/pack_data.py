#!/usr/bin/env python3
"""Create a small deployment snapshot from the full, reproducible local archive.

The complete NASA CSV remains local; every eligible detection is retained in
numeric arrays. Only the map response is sampled, with explicit shown/total.
"""
from pathlib import Path
import gzip
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from backend.science import eligible_hotspots


def main():
    folder = ROOT / 'data' / 'processed'
    raw = pd.read_csv(folder / 'hotspots.csv', dtype={'confidence': str, 'acq_time': str})
    frame = eligible_hotspots(raw)
    if isinstance(frame, tuple):
        frame = frame[0]
    day = (pd.to_datetime(frame.acq_date) - pd.Timestamp('2001-01-01')).dt.days.to_numpy(dtype=np.int16)
    np.savez_compressed(folder / 'observations.npz',
                        latitude=frame.latitude.to_numpy(dtype=np.float32),
                        longitude=frame.longitude.to_numpy(dtype=np.float32),
                        day=day,
                        sensor=frame.sensor.eq('VIIRS').to_numpy(dtype=np.uint8),
                        frp=frame.frp.to_numpy(dtype=np.float32),
                        scan=frame.scan.to_numpy(dtype=np.float32),
                        track=frame.track.to_numpy(dtype=np.float32),
                        time=pd.to_numeric(frame.acq_time).to_numpy(dtype=np.uint16),
                        satellite=frame.satellite.map({'Terra': 0, 'Aqua': 1, 'N': 2, 'Suomi NPP': 2}).fillna(255).to_numpy(dtype=np.uint8))
    events = json.loads((folder / 'perimeters.json').read_text())
    if isinstance(events, dict):
        events = events.get('records', events.get('features', []))
    keep = ('id', 'name', 'year', 'area_ha', 'area_acres', 'latitude', 'longitude', 'complex_id', 'complex_name', 'agency', 'irwin_id')
    packed_events = [{k: event.get(k) for k in keep} for event in events]
    with gzip.open(folder / 'events.json.gz', 'wt') as handle:
        json.dump(packed_events, handle, separators=(',', ':'), allow_nan=False)
    analysis_path = folder / 'analysis.json'
    if not analysis_path.exists():
        raise SystemExit('Run scripts/analyze.py before packing the scientific artifact.')
    with gzip.open(folder / 'analysis.json.gz', 'wb') as handle:
        handle.write(analysis_path.read_bytes())
    print(json.dumps({'raw_detections': len(raw), 'eligible_detections': len(frame),
                      'modis': int(frame.sensor.eq('MODIS').sum()),
                      'viirs': int(frame.sensor.eq('VIIRS').sum()),
                      'deployment_files': {p.name: p.stat().st_size for p in folder.iterdir()
                                           if p.name in ('observations.npz', 'events.json.gz', 'analysis.json.gz', 'california.geojson')}}))


if __name__ == '__main__':
    main()

